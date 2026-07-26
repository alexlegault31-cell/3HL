"""
Recomputes the materialized `StandingsEntry` table for a season from the
live `TeamSeason` rows. Called after every import/delete/forfeit -- and
also on every plain view of /standings, so a roster change (team removed/
added) is reflected immediately without waiting for the next game --
so reads are always cheap, consistent, and fresh.

Tiebreak order: points -> wins -> goal differential -> goals for.
"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import StandingsEntry, Team, TeamSeason


async def recompute_standings(session: AsyncSession, season_id: int) -> list[StandingsEntry]:
    team_seasons = (
        await session.execute(
            select(TeamSeason)
            .join(Team, Team.id == TeamSeason.team_id)
            .where(TeamSeason.season_id == season_id, Team.is_active.is_(True))
        )
    ).scalars().all()

    old_entries_by_team = {
        entry.team_id: entry
        for entry in (
            await session.execute(select(StandingsEntry).where(StandingsEntry.season_id == season_id))
        ).scalars().all()
    }

    ranked = sorted(
        team_seasons,
        key=lambda ts: (-ts.points, -ts.wins, -ts.goal_diff, -ts.goals_for),
    )

    await session.execute(delete(StandingsEntry).where(StandingsEntry.season_id == season_id))
    await session.flush()

    entries: list[StandingsEntry] = []
    for rank, ts in enumerate(ranked, start=1):
        old = old_entries_by_team.get(ts.team_id)

        # This function now runs on every plain /standings view too (not
        # just after a real game), so naively snapshotting "current rank"
        # into previous_rank on every call would make the trend arrows
        # meaningless -- they'd just show movement since the last time
        # someone happened to look, not since the last actual game. Only
        # advance previous_rank when this team's underlying record
        # actually changed; otherwise keep whatever was already stored.
        record_changed = old is None or (old.wins, old.losses, old.ot_losses, old.points) != (ts.wins, ts.losses, ts.ot_losses, ts.points)
        if record_changed:
            new_previous_rank = old.rank if old is not None else None
        else:
            new_previous_rank = old.previous_rank if old.previous_rank is not None else old.rank

        entry = StandingsEntry(
            season_id=season_id,
            team_id=ts.team_id,
            rank=rank,
            previous_rank=new_previous_rank,
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
