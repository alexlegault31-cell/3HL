
"""
Entrypoint: `python -m bot.main`

Loads every cog, registers the guild-scoped slash command tree (guild-scoped
sync is instant; global sync can take up to an hour to propagate — fine for
a single-league bot), and starts the client.
"""
from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from bot.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("nehl-bot")

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.members = True

COGS = [
    "bot.cogs.admin",
    "bot.cogs.league",
    "bot.cogs.standings",
    "bot.cogs.leaders",
    "bot.cogs.awards",
    "bot.cogs.channel_updater",
]

class NEHLBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=settings.command_prefix, intents=INTENTS)

    async def setup_hook(self) -> None:
        for cog in COGS:
            try:
                await self.load_extension(cog)
                log.info("Loaded cog %s", cog)
            except Exception:
                log.exception("Failed to load cog %s", cog)

        # Slash command sync is best-effort at boot: a wrong DISCORD_GUILD_ID
        # or a bot that hasn't been invited to that guild yet would otherwise
        # raise here and crash the whole process before it ever connects to
        # Discord. Log and continue instead -- `!sync` (bot owner only, see
        # cogs/admin.py) can be run manually once the guild ID / invite is
        # sorted out, without needing a redeploy.
        try:
            guild = discord.Object(id=settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %d slash commands to guild %s", len(synced), settings.discord_guild_id)
        except discord.HTTPException:
            log.exception(
                "Slash command sync failed at startup (check DISCORD_GUILD_ID and that the bot "
                "has been invited with the 'applications.commands' scope). The bot will still "
                "connect; run the `!sync` text command once this is fixed."
            )

    async def on_ready(self):
        log.info("Logged in as %s (id=%s)", self.user, self.user.id if self.user else "?")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="the standings"))


async def main():
    bot = NEHLBot()
    async with bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
