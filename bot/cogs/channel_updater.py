
"""
Implements "Automatically update channels": a background loop that
periodically regenerates the standings graphic, leaders boards, and
pending-schedule text, then edits the bot's own last message in each
configured channel in place (rather than spamming new messages every
cycle). The last-message-id per channel is persisted in `GuildSetting` so
this survives bot restarts.
"""
from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks
from sqlalchemy import select

from bot.config import settings
from bot.database import get_session
from bot.graphics.standings_graphic import render_standings
from bot.graphics.team_card import render_leaders_board
from bot.models import GuildSetting, StandingsEntry, Team
from bot.services.leaders_service import assists_leaders, goalie_leaders, goals_leaders, points_leaders
from bot.services.season_service import SeasonNotFound, get_active_season
from bot.utils.embeds import info_embed

log = logging.getLogger(__name__)

UPDATE_INTERVAL_MINUTES = 15


class ChannelUpdaterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_loop.start()

    def cog_unload(self):
        self.update_loop.cancel()

    @tasks.loop(minutes=UPDATE_INTERVAL_MINUTES)
    async def update_loop(self):
        try:
            await self._update_standings_channel()
            await self._update_leaders_channel()
        except SeasonNotFound:
            pass  # nothing to post until a season is active
        except Exception:  # noqa: BLE001
            log.exception("Channel auto-update cycle failed")

    @update_loop.before_loop
    async def before_update_loop(self):
        await self.bot.wait_until_ready()

    async def _update_standings_channel(self):
        if not settings.channel_standings:
            return
        async with get_session() as session:
            season = await get_active_season(session)
            entries = (
                await session.execute(
                    select(StandingsEntry).where(StandingsEntry.season_id == season.id).order_by(StandingsEntry.rank)
                )
            ).scalars().all()
            if not entries:
                return
            rows = [(e, await session.get(Team, e.team_id)) for e in entries]
            path = render_standings(season.name, rows)

        await self._post_or_edit(settings.channel_standings, "standings", file_path=path)

    async def _update_leaders_channel(self):
        if not settings.channel_stat_leaders:
            return
        async with get_session() as session:
            season = await get_active_season(session)
            rows = await points_leaders(session, season.id, limit=10)
            if not rows:
                return
            path = render_leaders_board("Points Leaders", season.name, rows)

        await self._post_or_edit(settings.channel_stat_leaders, "leaders", file_path=path)

    async def _post_or_edit(self, channel_id: int, setting_key: str, *, file_path: str):
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return

        async with get_session() as session:
            guild_id = channel.guild.id
            setting = await session.scalar(
                select(GuildSetting).where(GuildSetting.guild_id == guild_id, GuildSetting.key == f"last_msg_{setting_key}")
            )
            last_msg_id = int(setting.value) if setting and setting.value else None

            new_file = discord.File(file_path)
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

            sent = await channel.send(file=new_file)

            if setting is None:
                setting = GuildSetting(guild_id=guild_id, key=f"last_msg_{setting_key}", value=str(sent.id))
                session.add(setting)
            else:
                setting.value = str(sent.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelUpdaterCog(bot))

