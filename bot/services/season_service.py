
"""Small helper for resolving "current season" + season-number lookups,
used everywhere a command accepts an optional `season:` argument."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Season


class SeasonNotFound(Exception):
    pass


async def get_active_season(session: AsyncSession) -> Season:
    season = await session.scalar(select(Season).where(Season.is_active.is_(True)))
    if season is None:
        raise SeasonNotFound("No active season is set. Ask a commissioner to run `/season activate`.")
    return season


async def resolve_season(session: AsyncSession, number: Optional[int]) -> Season:
    if number is None:
        return await get_active_season(session)
    season = await session.scalar(select(Season).where(Season.number == number))
    if season is None:
        raise SeasonNotFound(f"Season {number} doesn't exist.")
    return season


async def set_active_season(session: AsyncSession, number: int) -> Season:
    season = await resolve_season(session, number)
    all_seasons = (await session.execute(select(Season))).scalars().all()
    for s in all_seasons:
        s.is_active = s.id == season.id
    return season

