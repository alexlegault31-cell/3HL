"""
Playoff bracket logic: seeding, series win tracking, and round
advancement. Single-elimination only.

The full bracket is built upfront by generate_bracket() -- every round's
series exist from the moment the bracket is created, with team_a_id/
team_b_id left null ("TBD") for any round beyond the first until the
previous round's winners are actually known. record_series_result()
automatically fills those slots in as each series is decided, and
schedules that matchup's first game the moment both slots are filled.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Game, PlayoffSeries, ScheduleGame, Team


class PlayoffError(RuntimeError):
    pass


def _bracket_order(n: int) -> list[int]:
    if n == 1:
        return [1]
    prev = _bracket_order(n // 2)
    result = []
    for s in prev:
        result.append(s)
        result.append(n + 1 - s)
    return result


def _round_name_for_series_count(series_count: int) -> str:
    return {1: "Finals", 2: "Semifinals", 4: "Quarterfinals"}.get(series_count, f"Round of {series_count * 2}")


async def _next_game_number(session: AsyncSession, season_id: int) -> int:
    existing = (await session.execute(select(ScheduleGame.game_number).where(ScheduleGame.season_id == season_id))).scalars().all()
    return (max(existing) + 1) if existing else 1


async def generate_bracket(session: AsyncSession, season_id: int, seeded_team_ids: list[int], best_of: int = 5) -> list[PlayoffSeries]:
    n = len(seeded_team_ids)
    if n < 2 or (n & (n - 1)) != 0:
        raise PlayoffError(f"Bracket size must be a power of 2 (2, 4, 8, 16...) -- got {n} teams.")
    if best_of % 2 == 0:
        raise PlayoffError("best_of must be an odd number (e.g. 3, 5, 7) so a series can't end in a tie.")

    order = _bracket_order(n)
    seed_to_team = {i + 1: seeded_team_ids[i] for i in range(n)}

    created: list[PlayoffSeries] = []

    # --- Round 1: real, known teams -- schedule each game right away. ---
    series_count = n // 2
    round_name = _round_name_for_series_count(series_count)
    for i in range(series_count):
        seed_a, seed_b = order[i * 2], order[i * 2 + 1]
        series = PlayoffSeries(
            season_id=season_id,
            round_name=round_name,
            round_order=1,
            series_order=i + 1,
            team_a_id=seed_to_team[seed_a],
            team_b_id=seed_to_team[seed_b],
            seed_a=seed_a,
            seed_b=seed_b,
            best_of=best_of,
        )
        session.add(series)
        await session.flush()
        created.append(series)

        game_number = await _next_game_number(session, season_id)
        session.add(
            ScheduleGame(
                season_id=season_id,
                game_number=game_number,
                is_playoffs=True,
                playoff_round=round_name,
                playoff_series_id=series.id,
                home_team_id=series.team_a_id,
                away_team_id=series.team_b_id,
            )
        )
        await session.flush()

    # --- Every subsequent round: TBD placeholders, no games scheduled
    # yet since we don't know who's actually playing. record_series_result
    # fills these in automatically as earlier rounds get decided. ---
    current_series_count = series_count
    round_order = 2
    while current_series_count > 1:
        next_series_count = current_series_count // 2
        next_round_name = _round_name_for_series_count(next_series_count)
        for i in range(next_series_count):
            series = PlayoffSeries(
                season_id=season_id,
                round_name=next_round_name,
                round_order=round_order,
                series_order=i + 1,
                team_a_id=None,
                team_b_id=None,
                best_of=best_of,
            )
            session.add(series)
            await session.flush()
            created.append(series)
        current_series_count = next_series_count
        round_order += 1

    return created


async def _propagate_winner(session: AsyncSession, series: PlayoffSeries) -> None:
    """Fills the winner of a just-decided series into its slot in the
    next round's already-existing placeholder series (built eagerly by
    generate_bracket), and schedules that matchup's first game the
    moment both of its slots are filled in."""
    next_round_order = series.round_order + 1
    next_series_order = (series.series_order + 1) // 2
    is_team_a_slot = (series.series_order % 2) == 1  # odd series_order -> team_a slot, even -> team_b slot

    next_series = await session.scalar(
        select(PlayoffSeries).where(
            PlayoffSeries.season_id == series.season_id,
            PlayoffSeries.round_order == next_round_order,
            PlayoffSeries.series_order == next_series_order,
        )
    )
    if next_series is None:
        return  # series was the Finals -- nothing further to propagate into

    if is_team_a_slot:
        next_series.team_a_id = series.winner_team_id
    else:
        next_series.team_b_id = series.winner_team_id
    await session.flush()

    if next_series.team_a_id is not None and next_series.team_b_id is not None:
        game_number = await _next_game_number(session, series.season_id)
        session.add(
            ScheduleGame(
                season_id=series.season_id,
                game_number=game_number,
                is_playoffs=True,
                playoff_round=next_series.round_name,
                playoff_series_id=next_series.id,
                home_team_id=next_series.team_a_id,
                away_team_id=next_series.team_b_id,
            )
        )
        await session.flush()


async def record_series_result(session: AsyncSession, schedule: ScheduleGame, game: Game) -> Optional[PlayoffSeries]:
    if schedule.playoff_series_id is None:
        return None

    series = await session.get(PlayoffSeries, schedule.playoff_series_id)
    if series is None or series.winner_team_id is not None:
        return series

    game_winner_id = game.home_team_id if game.home_score > game.away_score else game.away_team_id
    if game_winner_id == series.team_a_id:
        series.wins_a += 1
    elif game_winner_id == series.team_b_id:
        series.wins_b += 1

    if series.wins_a >= series.wins_needed:
        series.winner_team_id = series.team_a_id
    elif series.wins_b >= series.wins_needed:
        series.winner_team_id = series.team_b_id

    if series.winner_team_id is None:
        # Series not yet decided -- schedule the next game in it,
        # alternating home/away each game.
        games_played = series.wins_a + series.wins_b
        next_home, next_away = (
            (series.team_b_id, series.team_a_id) if games_played % 2 == 1 else (series.team_a_id, series.team_b_id)
        )
        game_number = await _next_game_number(session, series.season_id)
        session.add(
            ScheduleGame(
                season_id=series.season_id,
                game_number=game_number,
                is_playoffs=True,
                playoff_round=series.round_name,
                playoff_series_id=series.id,
                home_team_id=next_home,
                away_team_id=next_away,
            )
        )
    else:
        # Series just clinched -- automatically advance the winner into
        # the bracket's next round instead of waiting on a manual command.
        await _propagate_winner(session, series)

    await session.flush()
    return series


async def advance_round(session: AsyncSession, season_id: int, current_round_order: int) -> list[PlayoffSeries]:
    """Kept as a manual validation/lookup helper -- generate_bracket now
    builds every round upfront and record_series_result automatically
    fills in winners as series are decided, so this is no longer needed
    to CREATE anything in normal use. It just confirms the current round
    is fully decided and returns the next round's (already-populated)
    series list, useful as a sanity check or recovery path."""
    current = (
        await session.execute(
            select(PlayoffSeries)
            .where(PlayoffSeries.season_id == season_id, PlayoffSeries.round_order == current_round_order)
            .order_by(PlayoffSeries.series_order)
        )
    ).scalars().all()

    if not current:
        raise PlayoffError(f"No playoff round {current_round_order} found for this season.")

    undecided = [s for s in current if s.winner_team_id is None]
    if undecided:
        names = ", ".join(f"#{s.series_order}" for s in undecided)
        raise PlayoffError(f"Series {names} in {current[0].round_name} haven't been decided yet.")

    if len(current) == 1:
        raise PlayoffError(f"{current[0].round_name} is the final round -- there's nothing to advance to.")

    next_round_order = current_round_order + 1
    next_series = (
        await session.execute(
            select(PlayoffSeries)
            .where(PlayoffSeries.season_id == season_id, PlayoffSeries.round_order == next_round_order)
            .order_by(PlayoffSeries.series_order)
        )
    ).scalars().all()
    return next_series


async def get_bracket(session: AsyncSession, season_id: int) -> list[list[PlayoffSeries]]:
    all_series = (
        await session.execute(
            select(PlayoffSeries).where(PlayoffSeries.season_id == season_id).order_by(PlayoffSeries.round_order, PlayoffSeries.series_order)
        )
    ).scalars().all()

    rounds: dict[int, list[PlayoffSeries]] = {}
    for s in all_series:
        rounds.setdefault(s.round_order, []).append(s)
    return [rounds[k] for k in sorted(rounds.keys())]
