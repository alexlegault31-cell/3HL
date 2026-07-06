
"""
Recomputes the materialized `StandingsEntry` table for a season from the
live `TeamSeason` rows. Called after every import/delete/forfeit so reads
(`/standings`) are always cheap and consistent.

Tiebreak order: points -> wins -> goal differential -> goals for.
"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import StandingsEntry, TeamSeason


async def recompute_standings(session: AsyncSession, season_id: int) -> list[StandingsEntry]:
    team_seasons = (
        await session.execute(select(TeamSeason).where(TeamSeason.season_id == season_id))
    ).scalars().all()

    ranked = sorted(
        team_seasons,
        key=lambda ts: (-ts.points, -ts.wins, -ts.goal_diff, -ts.goals_for),
    )

    await session.execute(delete(StandingsEntry).where(StandingsEntry.season_id == season_id))
    await session.flush()

    entries: list[StandingsEntry] = []
    for rank, ts in enumerate(ranked, start=1):
        entry = StandingsEntry(
            season_id=season_id,
            team_id=ts.team_id,
            rank=rank,
            wins=ts.wins,
            losses=ts.losses,
            ot_losses=ts.ot_losses,
            points=ts.points,
            goals_for=ts.goals_for,
            goals_against=ts.goals_against,
            goal_diff=ts.goal_diff,
            streak=f"{ts.streak_type}{ts.streak_count}" if ts.streak_type else "-",
        )
        session.add(entry)
        entries.append(entry)

    await session.flush()
    return entries

