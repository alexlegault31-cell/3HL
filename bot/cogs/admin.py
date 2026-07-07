"""Bot-owner diagnostics: manual slash command sync, ping, basic error
surface for app command failures (permission denials, etc.)."""
from __future__ import annotations

import logging
import time

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot.config import settings
from bot.services.chelstats_client import split_proxy_credentials
from bot.utils.checks import commissioner_only
from bot.utils.embeds import error_embed, info_embed

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

    @app_commands.command(
        name="diagnose-network",
        description="Test direct vs proxy connectivity to a simple site and to EA's real API, separately",
    )
    @commissioner_only()
    async def diagnose_network(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        results = []
        test_site = "https://api.ipify.org?format=json"
        ea_url = "https://proclubs.ea.com/api/nhl/clubs/matches"
        ea_params = {"clubIds": 2555, "platform": "common-gen5", "matchType": "gameType5"}

        proxy_url, proxy_auth = split_proxy_credentials(settings.chelstats_proxy_url)

        probes = [
            ("Simple site, DIRECT (no proxy)", test_site, None, None, None),
            ("Simple site, VIA PROXY", test_site, None, proxy_url, proxy_auth),
            ("EA API, DIRECT (no proxy)", ea_url, ea_params, None, None),
            ("EA API, VIA PROXY", ea_url, ea_params, proxy_url, proxy_auth),
        ]

        for label, url, params, proxy, auth in probes:
            start = time.monotonic()
            try:
                headers = {
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.ea.com/",
                    "Origin": "https://www.ea.com",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                    ),
                }
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(
                        url, params=params, proxy=proxy, proxy_auth=auth, timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        elapsed = time.monotonic() - start
                        body_preview = (await resp.text())[:150]
                        results.append(f"✅ **{label}** — HTTP {resp.status} in {elapsed:.1f}s\n`{body_preview}`")
            except Exception as e:  # noqa: BLE001
                elapsed = time.monotonic() - start
                results.append(f"❌ **{label}** — {type(e).__name__} after {elapsed:.1f}s")

        if not settings.chelstats_proxy_url:
            results.append("\n⚠️ No `CHELSTATS_PROXY_URL` is currently set, so the proxy tests above were skipped (ran direct instead).")

        await interaction.followup.send(embed=info_embed("Network Diagnostic", "\n\n".join(results)), ephemeral=True)


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
