################################################################
FILE PATH TO TYPE ON GITHUB: bot/cogs/admin.py
################################################################
"""Bot-owner diagnostics: manual slash command sync, ping, basic error
surface for app command failures (permission denials, etc.)."""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import settings
from bot.utils.embeds import error_embed

log = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="sync")
    @commands.is_owner()
    async def sync(self, ctx: commands.Context):
        guild = discord.Object(id=settings.discord_guild_id)
        self.bot.tree.copy_global_to(guild=guild)
        synced = await self.bot.tree.sync(guild=guild)
        await ctx.send(f"Synced {len(synced)} commands to guild {settings.discord_guild_id}.")

    @app_commands.command(name="ping", description="Check the bot is alive")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🏓 Pong! `{round(self.bot.latency * 1000)}ms`", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))

    @bot.tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            msg = embed_for_permission_error()
            if interaction.response.is_done():
                await interaction.followup.send(embed=msg, ephemeral=True)
            else:
                await interaction.response.send_message(embed=msg, ephemeral=True)
            return

        log.exception("Unhandled app command error", exc_info=error)
        msg = error_embed("Something went wrong", "An unexpected error occurred. The commissioner team has been notified.")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=msg, ephemeral=True)
            else:
                await interaction.response.send_message(embed=msg, ephemeral=True)
        except discord.HTTPException:
            pass


def embed_for_permission_error() -> discord.Embed:
    return error_embed("Permission denied", "You don't have the required role to run this command.")

===== END OF FILE, COPY UP TO HERE =====
