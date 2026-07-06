
################################################################
FILE PATH TO TYPE ON GITHUB: bot/services/leaders_service.py
################################################################
"""
Queries backing `/leaders goals|assists|points|goalie`. Always season-
scoped; "leaders" with no season specified means the currently active
season (resolved by the caller via season_service.get_active_season).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Player, PlayerSeason, Team


@dataclass
class LeaderRow:
    rank: int
    player: Player
    team: Team | None
    value: float
    secondary: str = ""


MIN_GOALIE_GAMES = 1


async def goals_leaders(session: AsyncSession, season_id: int, limit: int = 10) -> list[LeaderRow]:
    stmt = (
        select(PlayerSeason, Player, Team)
        .join(Player, Player.id == PlayerSeason.player_id)
        .outerjoin(Team, Team.id == PlayerSeason.team_id)
        .where(PlayerSeason.season_id == season_id, Player.is_goalie.is_(False))
        .order_by(PlayerSeason.goals.desc(), PlayerSeason.points.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        LeaderRow(rank=i + 1, player=p, team=t, value=ps.goals, secondary=f"{ps.games_played} GP")
        for i, (ps, p, t) in enumerate(rows)
    ]


async def assists_leaders(session: AsyncSession, season_id: int, limit: int = 10) -> list[LeaderRow]:
    stmt = (
        select(PlayerSeason, Player, Team)
        .join(Player, Player.id == PlayerSeason.player_id)
        .outerjoin(Team, Team.id == PlayerSeason.team_id)
        .where(PlayerSeason.season_id == season_id, Player.is_goalie.is_(False))
        .order_by(PlayerSeason.assists.desc(), PlayerSeason.points.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        LeaderRow(rank=i + 1, player=p, team=t, value=ps.assists, secondary=f"{ps.games_played} GP")
        for i, (ps, p, t) in enumerate(rows)
    ]


async def points_leaders(session: AsyncSession, season_id: int, limit: int = 10) -> list[LeaderRow]:
    stmt = (
        select(PlayerSeason, Player, Team)
        .join(Player, Player.id == PlayerSeason.player_id)
        .outerjoin(Team, Team.id == PlayerSeason.team_id)
        .where(PlayerSeason.season_id == season_id, Player.is_goalie.is_(False))
        .order_by(PlayerSeason.points.desc(), PlayerSeason.goals.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        LeaderRow(rank=i + 1, player=p, team=t, value=ps.points, secondary=f"{ps.goals}G {ps.assists}A")
        for i, (ps, p, t) in enumerate(rows)
    ]


async def goalie_leaders(session: AsyncSession, season_id: int, limit: int = 10) -> list[LeaderRow]:
    """Ranked by save %, min `MIN_GOALIE_GAMES` GP to qualify."""
    stmt = (
        select(PlayerSeason, Player, Team)
        .join(Player, Player.id == PlayerSeason.player_id)
        .outerjoin(Team, Team.id == PlayerSeason.team_id)
        .where(
            PlayerSeason.season_id == season_id,
            Player.is_goalie.is_(True),
            PlayerSeason.games_played >= MIN_GOALIE_GAMES,
        )
    )
    rows = (await session.execute(stmt)).all()
    scored = sorted(rows, key=lambda r: (-r[0].save_pct, r[0].gaa))
    return [
        LeaderRow(
            rank=i + 1,
            player=p,
            team=t,
            value=ps.save_pct,
            secondary=f"{ps.wins}-{ps.losses}-{ps.ot_losses}, {ps.gaa} GAA",
        )
        for i, (ps, p, t) in enumerate(scored[:limit])
    ]

===== END OF FILE, COPY UP TO HERE =====
