"""
The core import pipeline behind `/league admin submit-game`.

Pipeline:
  1. Look up the ScheduleGame for (season, game_number).
  2. Resolve home/away TeamSeason -> linked Club IDs.
  3. Pull recent match history for both clubs from EA's Pro Clubs API.
  4. Intersect to find the match both clubs share, not already imported.
  5. Fetch full box score for that match.
  6. Persist Game + PlayerGameStat/GoalieGameStat/TeamGameStat permanently.
  7. Upsert PlayerSeason aggregates (incremental, never a full season
     recompute, so historical seasons are untouched).
  8. If this is a REGULAR SEASON game (not playoffs): upsert TeamSeason
     aggregates and recompute the standings table.
  9. Return an ImportResult the cog uses to post graphics + recap, and to
     feed into playoff_service.record_series_result if it's a playoff game.

IMPORTANT: playoff games deliberately do NOT touch TeamSeason or the
StandingsEntry table -- the regular season standings should only ever
reflect regular season results. Playoff series results live entirely in
PlayoffSeries (see services/playoff_service.py). This was a real bug in
an earlier version of this file where playoff forfeits/imports were
incorrectly being added to the regular season win/loss/points totals.

`reverse_game()` undoes step 6-8 for `/league admin delete-game`, walking
the stored PlayerGameStat/GoalieGameStat/TeamGameStat rows (NOT
re-deriving deltas from the live API, which could have changed) and
subtracting them back out of the season aggregates -- again skipping the
TeamSeason/standings step entirely for playoff games, since those were
never touched in the first place.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import (
    Game,
    GameImport,
    GoalieGameStat,
    Player,
    PlayerGameStat,
    PlayerSeason,
    PlayerTeamLink,
    ScheduleGame,
    Season,
    Team,
    TeamGameStat,
    TeamSeason,
)
from bot.models.schedule import ScheduleStatus
from bot.services.chelstats_client import ChelStatsClient, MatchDetail, combine_matches
from bot.services.standings_service import recompute_standings

log = logging.getLogger(__name__)


class ImportError_(RuntimeError):
    """Raised for any expected/user-facing import failure."""


@dataclass
class ImportResult:
    game: Game
    schedule: ScheduleGame
    home_team: Team
    away_team: Team
    player_lines: list[PlayerGameStat]
    goalie_lines: list[GoalieGameStat]
    was_merged: bool = False


async def import_game(
    session: AsyncSession,
    *,
    season_id: int,
    game_number: int,
    imported_by_discord_id: int,
    client: Optional[ChelStatsClient] = None,
    disable_auto_merge: bool = False,
) -> ImportResult:
    client = client or ChelStatsClient()

    schedule = await _get_schedule_game(session, season_id, game_number)
    if schedule.status == ScheduleStatus.PLAYED:
        raise ImportError_(f"Game #{game_number} has already been imported.")
    if schedule.status == ScheduleStatus.FORFEITED:
        raise ImportError_(f"Game #{game_number} was recorded as a forfeit. Use `/league admin edit-game` to override.")

    home_ts = await _get_team_season(session, schedule.home_team_id, season_id)
    away_ts = await _get_team_season(session, schedule.away_team_id, season_id)

    # Fetch these explicitly rather than accessing schedule.home_team /
    # schedule.away_team (lazy relationship access), which crashes with
    # MissingGreenlet outside of specific contexts SQLAlchemy's asyncio
    # extension supports for implicit lazy loading.
    home_team_obj = await session.get(Team, schedule.home_team_id)
    away_team_obj = await session.get(Team, schedule.away_team_id)

    if not home_ts.club_id:
        raise ImportError_(f"{home_team_obj.name} has no linked Club ID. Run `/league club swap` first.")
    if not away_ts.club_id:
        raise ImportError_(f"{away_team_obj.name} has no linked Club ID. Run `/league club swap` first.")

    # Playoff games skip auto-merge entirely: teams can legitimately play
    # each other multiple times in one night in a playoff series (unlike
    # the regular season schedule, which never repeats a matchup twice in
    # a row), so "two close-together matches" isn't a reliable lagout
    # signal there. The intended playoff workflow is submitting each game
    # right after it's played, which sidesteps the ambiguity entirely.
    allow_auto_merge = (not schedule.is_playoffs) and (not disable_auto_merge)
    match_detail = await _find_matching_match(client, home_ts.club_id, away_ts.club_id, allow_auto_merge=allow_auto_merge)
    if match_detail is None:
        raise ImportError_(
            f"Couldn't find a recent EASHL match between {home_team_obj.name} "
            f"(Club {home_ts.club_id}) and {away_team_obj.name} (Club {away_ts.club_id}). "
            f"Make sure the game has been played and try again in a few minutes."
        )
    was_merged = "+" in match_detail.match_id  # combine_matches joins match_ids with "+"

    existing = await session.scalar(select(Game).where(Game.external_match_id == match_detail.match_id))
    if existing is not None:
        raise ImportError_(f"That EASHL match (`{match_detail.match_id}`) has already been imported as a game.")

    detail = match_detail

    if detail.home.club_id == home_ts.club_id:
        home_box, away_box = detail.home, detail.away
    else:
        home_box, away_box = detail.away, detail.home

    now = dt.datetime.now(dt.timezone.utc)

    game = Game(
        season_id=season_id,
        schedule_id=schedule.id,
        home_team_id=schedule.home_team_id,
        away_team_id=schedule.away_team_id,
        home_score=home_box.goals,
        away_score=away_box.goals,
        went_to_overtime=detail.went_to_overtime,
        went_to_shootout=detail.went_to_shootout,
        external_match_id=detail.match_id,
        played_at=dt.datetime.fromtimestamp(detail.timestamp, tz=dt.timezone.utc) if detail.timestamp else now,
        imported_at=now,
        imported_by_discord_id=imported_by_discord_id,
        is_forfeit=False,
    )
    session.add(game)
    await session.flush()

    session.add(
        GameImport(
            game_id=game.id,
            source="ea_pro_clubs",
            raw_payload=detail.raw,
            fetched_at=now,
        )
    )

    session.add(
        TeamGameStat(
            game_id=game.id,
            team_id=schedule.home_team_id,
            season_id=season_id,
            goals=home_box.goals,
            shots=home_box.shots,
            hits=home_box.hits,
            pim=home_box.pim,
            powerplay_goals=home_box.powerplay_goals,
            powerplay_opportunities=home_box.powerplay_opportunities,
        )
    )
    session.add(
        TeamGameStat(
            game_id=game.id,
            team_id=schedule.away_team_id,
            season_id=season_id,
            goals=away_box.goals,
            shots=away_box.shots,
            hits=away_box.hits,
            pim=away_box.pim,
            powerplay_goals=away_box.powerplay_goals,
            powerplay_opportunities=away_box.powerplay_opportunities,
        )
    )

    player_lines: list[PlayerGameStat] = []
    goalie_lines: list[GoalieGameStat] = []

    for box in detail.players:
        team_id = schedule.home_team_id if box.club_id == home_ts.club_id else schedule.away_team_id
        player = await _resolve_player(session, box.gamertag, box.external_player_id, box.is_goalie)
        await _ensure_team_link(session, player.id, team_id, season_id)

        if box.is_goalie:
            line = GoalieGameStat(
                game_id=game.id,
                player_id=player.id,
                team_id=team_id,
                season_id=season_id,
                result=1 if box.is_win else (2 if box.is_ot_loss else 0),
                shots_against=box.shots_against,
                saves=box.saves,
                goals_against=box.goals_against,
                minutes_played=box.minutes_played,
                shutout=(box.goals_against == 0 and box.minutes_played > 0),
                poke_checks=box.poke_checks,
                desperation_saves=box.desperation_saves,
            )
            session.add(line)
            goalie_lines.append(line)
            await _apply_goalie_season_delta(session, player.id, season_id, team_id, line)
        else:
            line = PlayerGameStat(
                game_id=game.id,
                player_id=player.id,
                team_id=team_id,
                season_id=season_id,
                goals=box.goals,
                assists=box.assists,
                points=box.goals + box.assists,
                plus_minus=box.plus_minus,
                hits=box.hits,
                pim=box.pim,
                shots=box.shots,
                ppg=box.ppg,
                faceoffs_won=box.faceoffs_won,
                faceoffs_lost=box.faceoffs_lost,
                takeaways=box.takeaways,
                interceptions=box.interceptions,
                blocked_shots=box.blocked_shots,
                giveaways=box.giveaways,
                pass_attempts=box.pass_attempts,
                passes_completed=box.passes_completed,
                position=box.position or None,
                minutes_played=box.minutes_played,
                time_with_puck=box.time_with_puck,
            )
            session.add(line)
            player_lines.append(line)
            await _apply_skater_season_delta(session, player.id, season_id, team_id, line)

    # Regular-season standings/records ONLY -- playoff games never touch
    # TeamSeason or the standings table. Playoff results live entirely in
    # PlayoffSeries (see playoff_service.record_series_result, called by
    # the cog right after this function returns).
    if not schedule.is_playoffs:
        await apply_team_season_delta(session, schedule.home_team_id, season_id, home_box.goals, away_box.goals, detail.went_to_overtime)
        await apply_team_season_delta(session, schedule.away_team_id, season_id, away_box.goals, home_box.goals, detail.went_to_overtime)

    schedule.status = ScheduleStatus.PLAYED
    schedule.game_id = game.id

    await session.flush()
    if not schedule.is_playoffs:
        await recompute_standings(session, season_id)

    home_team = await session.get(Team, schedule.home_team_id)
    away_team = await session.get(Team, schedule.away_team_id)

    return ImportResult(
        game=game,
        schedule=schedule,
        home_team=home_team,  # type: ignore[arg-type]
        away_team=away_team,  # type: ignore[arg-type]
        player_lines=player_lines,
        goalie_lines=goalie_lines,
        was_merged=was_merged,
    )


async def reverse_game(session: AsyncSession, game: Game) -> None:
    """Used by /league admin delete-game. Subtracts this game's stat lines
    back out of every PLAYER season aggregate, then deletes the Game row.
    TeamSeason/standings are only touched (and thus only need reversing)
    if this was a regular season game -- playoff games never affected
    them in the first place."""
    player_lines = (await session.execute(select(PlayerGameStat).where(PlayerGameStat.game_id == game.id))).scalars().all()
    goalie_lines = (await session.execute(select(GoalieGameStat).where(GoalieGameStat.game_id == game.id))).scalars().all()

    for line in player_lines:
        ps = await _get_player_season(session, line.player_id, line.season_id)
        if ps:
            ps.games_played -= 1
            ps.goals -= line.goals
            ps.assists -= line.assists
            ps.points -= line.points
            ps.plus_minus -= line.plus_minus
            ps.hits -= line.hits
            ps.pim -= line.pim
            ps.shots -= line.shots
            ps.ppg -= line.ppg
            ps.faceoffs_won -= line.faceoffs_won
            ps.faceoffs_lost -= line.faceoffs_lost
            ps.takeaways -= line.takeaways
            ps.interceptions -= line.interceptions
            ps.blocked_shots -= line.blocked_shots
            ps.giveaways -= line.giveaways
            ps.pass_attempts -= line.pass_attempts
            ps.passes_completed -= line.passes_completed

    for line in goalie_lines:
        ps = await _get_player_season(session, line.player_id, line.season_id)
        if ps:
            ps.games_played -= 1
            ps.wins -= 1 if line.result == 1 else 0
            ps.losses -= 1 if line.result == 0 else 0
            ps.ot_losses -= 1 if line.result == 2 else 0
            ps.shots_against -= line.shots_against
            ps.saves -= line.saves
            ps.goals_against -= line.goals_against
            ps.shutouts -= 1 if line.shutout else 0
            ps.minutes_played -= line.minutes_played
            ps.poke_checks -= line.poke_checks
            ps.desperation_saves -= line.desperation_saves

    schedule = None
    if game.schedule_id:
        schedule = await session.get(ScheduleGame, game.schedule_id)

    is_playoff_game = schedule.is_playoffs if schedule else False

    if not is_playoff_game:
        home_ts = await _get_team_season(session, game.home_team_id, game.season_id)
        away_ts = await _get_team_season(session, game.away_team_id, game.season_id)
        undo_team_result(home_ts, game.home_score, game.away_score, game.went_to_overtime)
        undo_team_result(away_ts, game.away_score, game.home_score, game.went_to_overtime)

    if schedule:
        schedule.status = ScheduleStatus.SCHEDULED
        schedule.game_id = None

    season_id = game.season_id
    await session.delete(game)
    await session.flush()
    if not is_playoff_game:
        await recompute_standings(session, season_id)


async def find_pending_schedule_for_matchup(
    session: AsyncSession, season_id: int, team_a_id: int, team_b_id: int
) -> Optional[ScheduleGame]:
    """Auto-finds the correct not-yet-played ScheduleGame between two
    teams, so /league admin forfeit-game can link a forfeit to the right
    series/schedule slot WITHOUT the commissioner having to look up and
    type the exact game number -- a real source of user error, since a
    forgotten game_number meant a playoff forfeit silently never updated
    the series score. Prefers a playoff-tagged pending game (since that's
    the more error-prone case) over a regular season one, and the lowest
    game_number if there are multiple matches."""
    stmt = (
        select(ScheduleGame)
        .where(
            ScheduleGame.season_id == season_id,
            ScheduleGame.status == ScheduleStatus.SCHEDULED,
            (
                ((ScheduleGame.home_team_id == team_a_id) & (ScheduleGame.away_team_id == team_b_id))
                | ((ScheduleGame.home_team_id == team_b_id) & (ScheduleGame.away_team_id == team_a_id))
            ),
        )
        .order_by(ScheduleGame.is_playoffs.desc(), ScheduleGame.game_number.asc())
    )
    return await session.scalar(stmt)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _get_schedule_game(session: AsyncSession, season_id: int, game_number: int) -> ScheduleGame:
    stmt = select(ScheduleGame).where(
        ScheduleGame.season_id == season_id, ScheduleGame.game_number == game_number
    )
    schedule = await session.scalar(stmt)
    if schedule is None:
        raise ImportError_(f"No schedule entry found for game #{game_number} in this season.")
    return schedule


async def _get_team_season(session: AsyncSession, team_id: int, season_id: int) -> TeamSeason:
    stmt = select(TeamSeason).where(TeamSeason.team_id == team_id, TeamSeason.season_id == season_id)
    ts = await session.scalar(stmt)
    if ts is None:
        raise ImportError_("Team is not registered for this season. Run `/league club add` / season setup first.")
    return ts


LAGOUT_MERGE_WINDOW_MINUTES = 60


async def _find_matching_match(
    client: ChelStatsClient, home_club_id: int, away_club_id: int, *, allow_auto_merge: bool = True
) -> Optional[MatchDetail]:
    home_matches = await client.get_recent_club_matches(home_club_id)
    away_match_ids = {m.match_id for m in await client.get_recent_club_matches(away_club_id)}

    candidates = [m for m in home_matches if m.match_id in away_match_ids]
    if not candidates:
        return None
    candidates.sort(key=lambda m: m.timestamp, reverse=True)

    most_recent = candidates[0]
    if not allow_auto_merge:
        return most_recent

    # Two regular-season matches between the SAME two clubs, close
    # together in time, are never two separate legitimate games -- the
    # schedule would never pit them against each other twice in one
    # night. That signature (not a specific "disconnect" flag, since EA's
    # API doesn't expose one) is what identifies a lagout/reconnect split
    # into multiple match records. Walk backward from the most recent
    # match, absorbing any immediately-preceding match within the merge
    # window, and combine them into one game if more than one is found.
    to_merge = [most_recent]
    for candidate in candidates[1:]:
        last = to_merge[-1]
        gap_seconds = last.timestamp - candidate.timestamp
        if 0 <= gap_seconds <= LAGOUT_MERGE_WINDOW_MINUTES * 60:
            to_merge.append(candidate)
        else:
            break  # candidates are sorted newest-first, so the gap only grows from here

    if len(to_merge) == 1:
        return most_recent
    return combine_matches(to_merge)


async def _resolve_player(session: AsyncSession, gamertag: str, external_id: Optional[str], is_goalie: bool) -> Player:
    player = await session.scalar(select(Player).where(Player.gamertag == gamertag))
    if player is None:
        player = Player(gamertag=gamertag, external_player_id=external_id, is_goalie=is_goalie)
        session.add(player)
        await session.flush()
    else:
        if external_id and not player.external_player_id:
            player.external_player_id = external_id
        player.is_goalie = is_goalie
    return player


async def _ensure_team_link(session: AsyncSession, player_id: int, team_id: int, season_id: int) -> None:
    stmt = select(PlayerTeamLink).where(
        PlayerTeamLink.player_id == player_id,
        PlayerTeamLink.season_id == season_id,
        PlayerTeamLink.team_id == team_id,
    )
    link = await session.scalar(stmt)
    if link is None:
        session.add(PlayerTeamLink(player_id=player_id, team_id=team_id, season_id=season_id, is_current=True))


async def _get_player_season(session: AsyncSession, player_id: int, season_id: int) -> Optional[PlayerSeason]:
    stmt = select(PlayerSeason).where(PlayerSeason.player_id == player_id, PlayerSeason.season_id == season_id)
    return await session.scalar(stmt)


async def _get_or_create_player_season(session: AsyncSession, player_id: int, season_id: int, team_id: int) -> PlayerSeason:
    ps = await _get_player_season(session, player_id, season_id)
    if ps is None:
        ps = PlayerSeason(player_id=player_id, season_id=season_id, team_id=team_id)
        session.add(ps)
        await session.flush()
    else:
        ps.team_id = team_id
    return ps


async def _apply_skater_season_delta(session: AsyncSession, player_id: int, season_id: int, team_id: int, line: PlayerGameStat) -> None:
    ps = await _get_or_create_player_season(session, player_id, season_id, team_id)
    ps.games_played += 1
    ps.goals += line.goals
    ps.assists += line.assists
    ps.points += line.points
    ps.plus_minus += line.plus_minus
    ps.hits += line.hits
    ps.pim += line.pim
    ps.shots += line.shots
    ps.ppg += line.ppg
    ps.faceoffs_won += line.faceoffs_won
    ps.faceoffs_lost += line.faceoffs_lost
    ps.takeaways += line.takeaways
    ps.interceptions += line.interceptions
    ps.blocked_shots += line.blocked_shots
    ps.giveaways += line.giveaways
    ps.pass_attempts += line.pass_attempts
    ps.passes_completed += line.passes_completed


async def _apply_goalie_season_delta(session: AsyncSession, player_id: int, season_id: int, team_id: int, line: GoalieGameStat) -> None:
    ps = await _get_or_create_player_season(session, player_id, season_id, team_id)
    ps.games_played += 1
    ps.wins += 1 if line.result == 1 else 0
    ps.losses += 1 if line.result == 0 else 0
    ps.ot_losses += 1 if line.result == 2 else 0
    ps.shots_against += line.shots_against
    ps.saves += line.saves
    ps.goals_against += line.goals_against
    ps.shutouts += 1 if line.shutout else 0
    ps.minutes_played += line.minutes_played
    ps.poke_checks += line.poke_checks
    ps.desperation_saves += line.desperation_saves


async def apply_team_season_delta(
    session: AsyncSession, team_id: int, season_id: int, goals_for: int, goals_against: int, went_ot: bool
) -> None:
    ts = await _get_team_season(session, team_id, season_id)
    ts.goals_for += goals_for
    ts.goals_against += goals_against

    if goals_for > goals_against:
        ts.wins += 1
        ts.points += 2
        if went_ot:
            ts.ot_wins += 1  # subset of wins, not counted separately
            result = "T"
        else:
            result = "W"
    elif went_ot:
        ts.ot_losses += 1
        ts.points += 1
        result = "O"
    else:
        ts.losses += 1
        result = "L"

    if ts.streak_type == result:
        ts.streak_count += 1
    else:
        ts.streak_type = result
        ts.streak_count = 1

    last10 = (ts.last_10 or "")[-9:] + result
    ts.last_10 = last10


def undo_team_result(ts: TeamSeason, goals_for: int, goals_against: int, went_ot: bool) -> None:
    """Public, synchronous by design -- called directly (no await) by
    /league admin edit-game to reverse a team's record before reapplying
    a corrected score. Does no DB queries itself, just mutates the
    already-fetched TeamSeason object, so it never needed to be async."""
    ts.goals_for -= goals_for
    ts.goals_against -= goals_against
    if goals_for > goals_against:
        ts.wins -= 1
        ts.points -= 2
        if went_ot:
            ts.ot_wins -= 1
    elif went_ot:
        ts.ot_losses -= 1
        ts.points -= 1
    else:
        ts.losses -= 1
    if ts.last_10:
        ts.last_10 = ts.last_10[:-1] or None
