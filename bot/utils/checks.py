################################################################
FILE PATH TO TYPE ON GITHUB: bot/utils/checks.py
################################################################
"""discord.app_commands check decorators wrapping permissions_service so
cogs can just do `@commissioner_only()` / `@gm_only()` above a command."""
from __future__ import annotations

import discord
from discord import app_commands

from bot.services.permissions_service import is_commissioner, is_gm


def commissioner_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False
        return is_commissioner(interaction.user)

    return app_commands.check(predicate)


def gm_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False
        return is_gm(interaction.user)

    return app_commands.check(predicate)

===== END OF FILE, COPY UP TO HERE =====
