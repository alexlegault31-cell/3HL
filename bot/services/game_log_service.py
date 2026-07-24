"""Game-by-game history queries -- powers the expanded player card (full
per-game log) and the simple win/loss recap on team cards."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Game, GoalieGameStat, Player, PlayerGameStat, Team


@dataclass
class SkaterGameLogRow:
    opponent: Team
    is_home: bool
    position: Optional[str]
    goals: int
    assists: int
    points: int
    plus_minus: int
    shots: int
    hits: int
    pim: int
    takeaways: int
    interceptions: int
    blocked_shots: int
    played_at: object


@dataclass
class GoalieGameLogRow:
    opponent: Team
    is_home: bool
    result: str  # "W", "L", "OTL"
    shots_against: int
    saves: int
    goals_against: int
    minutes_played: float
    shutout: bool
    played_at: object


async def get_skater_game_log(session: AsyncSession, player_id: int, season_id: int, limit: int = 20) -> list[SkaterGameLogRow]:
    stmt = (
        select(PlayerGameStat, Game)
        .join(Game, Game.id == PlayerGameStat.game_id)
        .where(PlayerGameStat.player_id == player_id, PlayerGameStat.season_id == season_id)
        .order_by(Game.played_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()

    out = []
    for line, game in rows:
        is_home = game.home_team_id == line.team_id
        opponent_id = game.away_team_id if is_home else game.home_team_id
        opponent = await session.get(Team, opponent_id)
        out.append(
            SkaterGameLogRow(
                opponent=opponent,
                is_home=is_home,
                position=line.position,
                goals=line.goals,
                assists=line.assists,
                points=line.points,
                plus_minus=line.plus_minus,
                shots=line.shots,
                hits=line.hits,
                pim=line.pim,
                takeaways=line.takeaways,
                interceptions=line.interceptions,
                blocked_shots=line.blocked_shots,
                played_at=game.played_at,
            )
        )
    return out


async def get_goalie_game_log(session: AsyncSession, player_id: int, season_id: int, limit: int = 20) -> list[GoalieGameLogRow]:
    stmt = (
        select(GoalieGameStat, Game)
        .join(Game, Game.id == GoalieGameStat.game_id)
        .where(GoalieGameStat.player_id == player_id, GoalieGameStat.season_id == season_id)
        .order_by(Game.played_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()

    out = []
    for line, game in rows:
        is_home = game.home_team_id == line.team_id
        opponent_id = game.away_team_id if is_home else game.home_team_id
        opponent = await session.get(Team, opponent_id)
        result = "W" if line.result == 1 else ("OTL" if line.result == 2 else "L")
        out.append(
            GoalieGameLogRow(
                opponent=opponent,
                is_home=is_home,
                result=result,
                shots_against=line.shots_against,
                saves=line.saves,
                goals_against=line.goals_against,
                minutes_played=line.minutes_played,
                shutout=line.shutout,
                played_at=game.played_at,
            )
        )
    return out


@dataclass
class TeamRecentResult:
    opponent: Team
    is_home: bool
    goals_for: int
    goals_against: int
    is_win: bool
    is_ot: bool
    is_forfeit: bool
    played_at: object


async def get_team_recent_results(session: AsyncSession, team_id: int, season_id: int, limit: int = 5) -> list[TeamRecentResult]:
    """Simple recent-results recap for team cards -- just who they played
    and the final score, nothing more detailed than that."""
    stmt = (
        select(Game)
        .where(Game.season_id == season_id, or_(Game.home_team_id == team_id, Game.away_team_id == team_id))
        .order_by(Game.played_at.desc())
        .limit(limit)
    )
    games = (await session.execute(stmt)).scalars().all()

    out = []
    for g in games:
        is_home = g.home_team_id == team_id
        opponent_id = g.away_team_id if is_home else g.home_team_id
        opponent = await session.get(Team, opponent_id)
        goals_for = g.home_score if is_home else g.away_score
        goals_against = g.away_score if is_home else g.home_score
        out.append(
            TeamRecentResult(
                opponent=opponent,
                is_home=is_home,
                goals_for=goals_for,
                goals_against=goals_against,
                is_win=goals_for > goals_against,
                is_ot=g.went_to_overtime,
                is_forfeit=g.is_forfeit,
                played_at=g.played_at,
            )
        )
    return out
