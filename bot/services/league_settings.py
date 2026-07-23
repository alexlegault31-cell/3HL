"""Small shared helpers for league-wide (not per-team) branding settings:
the league logo (`/league admin add-logo`) and the optional custom
background photo (`/league admin add-background`). Both are stored as
GuildSettings so every graphic-producing command fetches them the same
way instead of each duplicating the same query."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import GuildSetting

LEAGUE_LOGO_KEY = "league_logo_url"
LEAGUE_BACKGROUND_KEY = "league_background_url"


async def get_league_logo_url(session: AsyncSession, guild_id: int) -> Optional[str]:
    setting = await session.scalar(
        select(GuildSetting).where(GuildSetting.guild_id == guild_id, GuildSetting.key == LEAGUE_LOGO_KEY)
    )
    return setting.value if setting else None


async def get_league_background_url(session: AsyncSession, guild_id: int) -> Optional[str]:
    setting = await session.scalar(
        select(GuildSetting).where(GuildSetting.guild_id == guild_id, GuildSetting.key == LEAGUE_BACKGROUND_KEY)
    )
    return setting.value if setting else None


async def set_league_background_url(session: AsyncSession, guild_id: int, url: Optional[str]) -> None:
    """Pass url=None to clear it -- this is what makes the background
    photo easy to remove: it just reverts every graphic to the built-in
    gradient-banner look with no other changes needed."""
    setting = await session.scalar(
        select(GuildSetting).where(GuildSetting.guild_id == guild_id, GuildSetting.key == LEAGUE_BACKGROUND_KEY)
    )
    if setting is None:
        if url is not None:
            session.add(GuildSetting(guild_id=guild_id, key=LEAGUE_BACKGROUND_KEY, value=url))
    else:
        setting.value = url
