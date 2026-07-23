"""
Playoff bracket logic: seeding, series win tracking, and round
advancement. Single-elimination only.

Bracket seeding
---------------
`_bracket_order(n)` produces the standard tournament seeding order (for
8 teams: 1v8, 4v5, 2v7, 3v6) so the top seeds can't meet until the later
rounds -- this is the same seeding method real single-elim brackets use
(recursively interleaving seed `s` with `n+1-s`).

Game-by-game pacing
--------------------
Rather than pre-creating every possible game in a best-of-N series up
front (some may never be played if a team sweeps), `generate_bracket`
only creates each series' FIRST game. `record_series_result` (called
right after a playoff game is imported/forfeited) updates the series
score and, if the series isn't decided yet, automatically creates the
next game in that series -- alternating home ice each game.

Reversal scope note
--------------------
If a playoff game is deleted (`/league admin delete-game`), this
reverses that series' win count and re-evaluates the winner, but does
NOT retroactively remove a "next game" schedule entry that may have
already been auto-created as a result of it. This is a deliberate scope
limitation -- deleting playoff games is rare, and a commissioner can
manually clean up an extra schedule entry with `/league schedule` tools
if this edge case comes up.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Game, PlayoffSeries, ScheduleGame, Team
from bot.models.schedule import ScheduleStatus


class PlayoffError(RuntimeError):
    pass


def _bracket_order(n: int) -> list[int]:
    """Standard tournament seeding order. n must be a power of 2."""
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
    """`seeded_team_ids` must be ordered strongest-to-weakest (e.g. current
    standings order) and its length must be a power of 2 (4, 8, 16...)."""
    n = len(seeded_team_ids)
    if n < 2 or (n & (n - 1)) != 0:
        raise PlayoffError(f"Bracket size must be a power of 2 (2, 4, 8, 16...) -- got {n} teams.")
    if best_of % 2 == 0:
        raise PlayoffError("best_of must be an odd number (e.g. 3, 5, 7) so a series can't end in a tie.")

    order = _bracket_order(n)
    # order[i] is a 1-based seed number; map back to the team id at that seed.
    seed_to_team = {i + 1: seeded_team_ids[i] for i in range(n)}

    series_count = n // 2
    round_name = _round_name_for_series_count(series_count)
    created: list[PlayoffSeries] = []

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

    return created


async def record_series_result(session: AsyncSession, schedule: ScheduleGame, game: Game) -> Optional[PlayoffSeries]:
    """Call this right after a playoff-tagged game is imported or
    forfeited. Updates the series score and, if undecided, creates the
    next game in the series automatically. Returns the series, or None
    if this game wasn't tagged as part of a playoff series."""
    if schedule.playoff_series_id is None:
        return None

    series = await session.get(PlayoffSeries, schedule.playoff_series_id)
    if series is None or series.winner_team_id is not None:
        return series  # already decided, or series row missing -- nothing to do

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
        # Series continues -- create the next game, alternating home ice.
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

    await session.flush()
    return series


async def advance_round(session: AsyncSession, season_id: int, current_round_order: int) -> list[PlayoffSeries]:
    """Pairs up the winners of every series in the given round (adjacent
    series_order values: 1&2 -> next round's series 1, 3&4 -> series 2,
    etc.) and creates the next round. Raises if any series in the
    current round hasn't been decided yet."""
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

    winners = [s.winner_team_id for s in current]
    next_series_count = len(winners) // 2
    next_round_name = _round_name_for_series_count(next_series_count)
    next_round_order = current_round_order + 1
    best_of = current[0].best_of

    created: list[PlayoffSeries] = []
    for i in range(next_series_count):
        team_a_id, team_b_id = winners[i * 2], winners[i * 2 + 1]
        series = PlayoffSeries(
            season_id=season_id,
            round_name=next_round_name,
            round_order=next_round_order,
            series_order=i + 1,
            team_a_id=team_a_id,
            team_b_id=team_b_id,
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
                playoff_round=next_round_name,
                playoff_series_id=series.id,
                home_team_id=team_a_id,
                away_team_id=team_b_id,
            )
        )
        await session.flush()

    return created


async def get_bracket(session: AsyncSession, season_id: int) -> list[list[PlayoffSeries]]:
    """Returns every round's series, grouped by round_order, ordered
    round-then-series -- ready for the bracket graphic to render."""
    all_series = (
        await session.execute(
            select(PlayoffSeries).where(PlayoffSeries.season_id == season_id).order_by(PlayoffSeries.round_order, PlayoffSeries.series_order)
        )
    ).scalars().all()

    rounds: dict[int, list[PlayoffSeries]] = {}
    for s in all_series:
        rounds.setdefault(s.round_order, []).append(s)
    return [rounds[k] for k in sorted(rounds.keys())]
