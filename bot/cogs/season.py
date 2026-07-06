
"""Season lifecycle commands: /season create, /season activate, /season list,
/season info. Commissioner-only except `info`/`list`."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.database import get_session
from bot.models import Season
from bot.utils.checks import commissioner_only
from bot.utils.embeds import error_embed, info_embed, success_embed
from sqlalchemy import select


class SeasonCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    season_group = app_commands.Group(name="season", description="Season management")

    @season_group.command(name="create", description="Create a new league season")
    @app_commands.describe(number="Season number, e.g. 3", name="Display name, defaults to 'Season N'")
    @commissioner_only()
    async def create(self, interaction: discord.Interaction, number: int, name: str | None = None):
        async with get_session() as session:
            existing = await session.scalar(select(Season).where(Season.number == number))
            if existing:
                await interaction.response.send_message(embed=error_embed("Season exists", f"Season {number} already exists."), ephemeral=True)
                return
            season = Season(number=number, name=name or f"Season {number}")
            session.add(season)
        await interaction.response.send_message(embed=success_embed("Season created", f"**{season.name}** has been created."))

    @season_group.command(name="activate", description="Set the active league season")
    @app_commands.describe(number="Season number to activate")
    @commissioner_only()
    async def activate(self, interaction: discord.Interaction, number: int):
        from bot.services.season_service import SeasonNotFound, set_active_season

        async with get_session() as session:
            try:
                season = await set_active_season(session, number)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Not found", str(e)), ephemeral=True)
                return
        await interaction.response.send_message(embed=success_embed("Season activated", f"**{season.name}** is now the active season."))

    @season_group.command(name="list", description="List all seasons")
    async def list_(self, interaction: discord.Interaction):
        async with get_session() as session:
            seasons = (await session.execute(select(Season).order_by(Season.number))).scalars().all()
        if not seasons:
            await interaction.response.send_message(embed=info_embed("No seasons", "No seasons have been created yet."))
            return
        lines = [f"{'⭐' if s.is_active else '▫️'} **{s.name}**" for s in seasons]
        await interaction.response.send_message(embed=info_embed("Seasons", "\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(SeasonCog(bot))

