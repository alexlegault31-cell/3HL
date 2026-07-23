"""
Auto-updates the #standings and #stat-leaders channels by editing the
bot's own last posted message in place (never spamming new messages).

This used to run on a fixed 15-minute timer. It now runs only when
triggered directly, right after a game/forfeit is successfully entered
(see the calls to `refresh_standings_channel` / `refresh_leaders_channel`
in `bot/cogs/game.py`) -- so the channels update exactly once per game,
immediately, instead of on a schedule that might lag behind or post when
nothing changed.
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
from bot.graphics.combined_leaders_board import render_combined_leaders_board
from bot.services.leaders_service import (
    assists_leaders,
    blocked_shots_leaders,
    faceoff_pct_leaders,
    gaa_leaders,
    goalie_leaders,
    goals_leaders,
    hits_leaders,
    interceptions_leaders,
    pim_leaders,
    points_leaders,
    shutouts_leaders,
    takeaways_leaders,
)
from bot.services.league_settings import get_league_logo_url
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

    rows = [(e, await session.get(Team, e.team_id)) for e in entries]
    path = await render_standings(season.name, rows, league_logo_url)
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

    path = await render_leaders_board("Points Leaders", season.name, rows, league_logo_url)
    await _post_or_edit(bot, session, settings.channel_stat_leaders, "leaders", file_path=path)


async def refresh_all_channels(bot: commands.Bot, session: AsyncSession) -> None:
    """Call this one function after any game/forfeit import or deletion --
    it's a no-op for any channel that isn't configured, and safely skips
    if there's no active season yet."""
    try:
        await refresh_standings_channel(bot, session)
        await refresh_leaders_channel(bot, session)
    except Exception:  # noqa: BLE001
        # Never let a channel-posting failure break the actual game import
        # that triggered it -- the game/stats are already saved by this point.
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
    """Kept as a cog only so it still loads cleanly alongside the others;
    all the real logic above is called directly from bot/cogs/game.py,
    not from anything on a timer in this class."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelUpdaterCog(bot))
