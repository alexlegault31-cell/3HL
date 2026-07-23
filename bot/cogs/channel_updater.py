"""
Auto-updates the #standings and #stat-leaders channels by editing the
bot's own last posted message in place. Runs right after a game/forfeit
is entered (see calls in bot/cogs/league.py), not on a timer.
"""
from __future__ import annotations

import logging

import discord
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.graphics.standings_graphic import render_standings
from bot.graphics.team_card import render_leaders_board
from bot.models import GuildSetting, StandingsEntry, Team
from bot.services.leaders_service import points_leaders
from bot.services.league_settings import get_league_background_url, get_league_logo_url
from bot.services.season_service import SeasonNotFound, get_active_season

log = logging.getLogger(__name__)


async def refresh_standings_channel(bot: commands.Bot, session: AsyncSession) -> None:
    if not settings.channel_standings:
        return
    try:
        season = await get_active_season(session)
    except SeasonNotFound:
        return

    entries = (
        await session.execute(
            select(StandingsEntry).where(StandingsEntry.season_id == season.id).order_by(StandingsEntry.rank)
        )
    ).scalars().all()
    if not entries:
        return

    channel = bot.get_channel(settings.channel_standings)
    league_logo_url = await get_league_logo_url(session, channel.guild.id) if channel else None
    background_url = await get_league_background_url(session, channel.guild.id) if channel else None

    rows = [(e, await session.get(Team, e.team_id)) for e in entries]
    path = await render_standings(season.name, rows, league_logo_url, background_url)
    await _post_or_edit(bot, session, settings.channel_standings, "standings", file_path=path)


async def refresh_leaders_channel(bot: commands.Bot, session: AsyncSession) -> None:
    if not settings.channel_stat_leaders:
        return
    try:
        season = await get_active_season(session)
    except SeasonNotFound:
        return

    rows = await points_leaders(session, season.id, limit=10)
    if not rows:
        return

    channel = bot.get_channel(settings.channel_stat_leaders)
    league_logo_url = await get_league_logo_url(session, channel.guild.id) if channel else None
    background_url = await get_league_background_url(session, channel.guild.id) if channel else None

    path = await render_leaders_board("Points Leaders", season.name, rows, league_logo_url, background_url)
    await _post_or_edit(bot, session, settings.channel_stat_leaders, "leaders", file_path=path)


async def refresh_all_channels(bot: commands.Bot, session: AsyncSession) -> None:
    try:
        await refresh_standings_channel(bot, session)
        await refresh_leaders_channel(bot, session)
    except Exception:
        log.exception("Failed to refresh auto-update channels")


async def _post_or_edit(bot: commands.Bot, session: AsyncSession, channel_id: int, setting_key: str, *, file_path: str) -> None:
    channel = bot.get_channel(channel_id)
    if channel is None:
        return

    guild_id = channel.guild.id
    setting = await session.scalar(
        select(GuildSetting).where(GuildSetting.guild_id == guild_id, GuildSetting.key == f"last_msg_{setting_key}")
    )
    last_msg_id = int(setting.value) if setting and setting.value else None

    message = None
    if last_msg_id:
        try:
            message = await channel.fetch_message(last_msg_id)
        except (discord.NotFound, discord.Forbidden):
            message = None

    if message:
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    sent = await channel.send(file=discord.File(file_path))

    if setting is None:
        setting = GuildSetting(guild_id=guild_id, key=f"last_msg_{setting_key}", value=str(sent.id))
        session.add(setting)
    else:
        setting.value = str(sent.id)


class ChannelUpdaterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelUpdaterCog(bot))
