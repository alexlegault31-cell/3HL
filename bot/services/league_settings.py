"""Small shared helper for the league-wide (not per-team) logo, set via
`/league admin add-logo` and stored as a GuildSetting. Centralized here so
every graphic-producing command fetches it the same way instead of each
duplicating the same query."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import GuildSetting

LEAGUE_LOGO_KEY = "league_logo_url"


async def get_league_logo_url(session: AsyncSession, guild_id: int) -> Optional[str]:
    setting = await session.scalar(
        select(GuildSetting).where(GuildSetting.guild_id == guild_id, GuildSetting.key == LEAGUE_LOGO_KEY)
    )
    return setting.value if setting else None
