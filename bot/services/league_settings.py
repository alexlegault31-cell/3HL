"""Small shared helpers for league-wide (not per-team) branding settings:
the league logo (`/league admin add-logo`) and the optional custom
background photo (`/league admin add-background`). Both are stored as
GuildSettings so every graphic-producing command fetches them the same
way instead of each duplicating the same query.

Also stores the league's configurable weekly schedule pattern -- since
different leagues run on different days/times/games-per-night, this
isn't hardcoded, and can optionally have a separate pattern just for the
first week (e.g. a league starting on a single Wednesday before settling
into its normal Tue/Wed/Thu rotation)."""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import GuildSetting

LEAGUE_LOGO_KEY = "league_logo_url"
LEAGUE_BACKGROUND_KEY = "league_background_url"
SCHEDULE_PATTERN_KEY = "schedule_pattern"
SCHEDULE_FIRST_WEEK_PATTERN_KEY = "schedule_first_week_pattern"

# Used only if a league has never configured its own pattern.
DEFAULT_SCHEDULE_PATTERN = [
    "Tuesday 8:00 PM EST", "Tuesday 8:30 PM EST", "Tuesday 9:00 PM EST", "Tuesday 9:30 PM EST",
    "Wednesday 8:00 PM EST", "Wednesday 8:30 PM EST", "Wednesday 9:00 PM EST", "Wednesday 9:30 PM EST",
    "Thursday 8:00 PM EST", "Thursday 8:30 PM EST", "Thursday 9:00 PM EST", "Thursday 9:30 PM EST",
]


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


async def get_schedule_pattern(session: AsyncSession, guild_id: int) -> list[str]:
    """The recurring weekly slot pattern, as a list of 'Day Time' strings
    e.g. ["Tuesday 8:00 PM EST", "Wednesday 8:00 PM EST", ...], cycled
    through in order as games are generated. Falls back to a sensible
    default if this league has never configured its own."""
    setting = await session.scalar(
        select(GuildSetting).where(GuildSetting.guild_id == guild_id, GuildSetting.key == SCHEDULE_PATTERN_KEY)
    )
    if setting is None:
        return DEFAULT_SCHEDULE_PATTERN
    return json.loads(setting.value)


async def set_schedule_pattern(session: AsyncSession, guild_id: int, slots: list[str]) -> None:
    setting = await session.scalar(
        select(GuildSetting).where(GuildSetting.guild_id == guild_id, GuildSetting.key == SCHEDULE_PATTERN_KEY)
    )
    value = json.dumps(slots)
    if setting is None:
        session.add(GuildSetting(guild_id=guild_id, key=SCHEDULE_PATTERN_KEY, value=value))
    else:
        setting.value = value


async def get_schedule_first_week_pattern(session: AsyncSession, guild_id: int) -> Optional[list[str]]:
    """Optional override used ONLY for week 1 -- e.g. a league starting
    on a single day before settling into its normal rotation from week 2
    onward. Returns None if no override is configured (the regular
    pattern is used for every week including the first)."""
    setting = await session.scalar(
        select(GuildSetting).where(GuildSetting.guild_id == guild_id, GuildSetting.key == SCHEDULE_FIRST_WEEK_PATTERN_KEY)
    )
    if setting is None:
        return None
    return json.loads(setting.value)


async def set_schedule_first_week_pattern(session: AsyncSession, guild_id: int, slots: Optional[list[str]]) -> None:
    """Pass slots=None to clear the override, reverting week 1 to use
    the regular pattern like every other week."""
    setting = await session.scalar(
        select(GuildSetting).where(GuildSetting.guild_id == guild_id, GuildSetting.key == SCHEDULE_FIRST_WEEK_PATTERN_KEY)
    )
    if slots is None:
        if setting is not None:
            await session.delete(setting)
        return
    value = json.dumps(slots)
    if setting is None:
        session.add(GuildSetting(guild_id=guild_id, key=SCHEDULE_FIRST_WEEK_PATTERN_KEY, value=value))
    else:
        setting.value = value
