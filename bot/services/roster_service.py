"""Roster query for the club stats card -- every player who's played at
least one game for this team this season, split into skaters and
goalies since they show different stat columns."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Player, PlayerSeason


@dataclass
class RosterSkaterRow:
    gamertag: str
    games_played: int
    goals: int
    assists: int
    points: int
    ppg: int


@dataclass
class RosterGoalieRow:
    gamertag: str
    games_played: int
    goals_against: int
    gaa: float
    saves: int
    save_pct: float
    shutouts: int


async def get_team_roster(session: AsyncSession, team_id: int, season_id: int) -> tuple[list[RosterSkaterRow], list[RosterGoalieRow]]:
    """Returns (skaters, goalies) -- only players with at least one game
    played for this team this season, sorted by points/GAA respectively."""
    stmt = (
        select(PlayerSeason, Player)
        .join(Player, Player.id == PlayerSeason.player_id)
        .where(PlayerSeason.team_id == team_id, PlayerSeason.season_id == season_id, PlayerSeason.games_played > 0)
    )
    rows = (await session.execute(stmt)).all()

    skaters = []
    goalies = []
    for ps, player in rows:
        if player.is_goalie:
            goalies.append(
                RosterGoalieRow(
                    gamertag=player.gamertag,
                    games_played=ps.games_played,
                    goals_against=ps.goals_against,
                    gaa=ps.gaa,
                    saves=ps.saves,
                    save_pct=ps.save_pct,
                    shutouts=ps.shutouts,
                )
            )
        else:
            skaters.append(
                RosterSkaterRow(
                    gamertag=player.gamertag,
                    games_played=ps.games_played,
                    goals=ps.goals,
                    assists=ps.assists,
                    points=ps.points,
                    ppg=ps.ppg,
                )
            )

    skaters.sort(key=lambda r: r.points, reverse=True)
    goalies.sort(key=lambda r: r.gaa)
    return skaters, goalies
