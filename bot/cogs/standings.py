"""`/standings` -- always posts the visual standings graphic."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.database import get_session
from bot.graphics.standings_graphic import render_standings
from bot.models import StandingsEntry, Team
from bot.services.league_settings import get_league_background_url, get_league_logo_url
from bot.services.season_service import SeasonNotFound, resolve_season
from bot.utils.embeds import error_embed, info_embed


class StandingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="standings", description="View the league standings")
    @app_commands.describe(season="Season number (defaults to active)")
    async def standings(self, interaction: discord.Interaction, season: int | None = None):
        await interaction.response.defer()
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.followup.send(embed=error_embed("Season error", str(e)))
                return

            stmt = select(StandingsEntry).where(StandingsEntry.season_id == s.id).order_by(StandingsEntry.rank)
            entries = (await session.execute(stmt)).scalars().all()
            if not entries:
                await interaction.followup.send(embed=info_embed("No standings yet", f"No games have been played in {s.name}."))
                return

            rows = [(e, await session.get(Team, e.team_id)) for e in entries]
            league_logo_url = await get_league_logo_url(session, interaction.guild_id)
            background_url = await get_league_background_url(session, interaction.guild_id)
            path = await render_standings(s.name, rows, league_logo_url, background_url)

        await interaction.followup.send(file=discord.File(path))


async def setup(bot: commands.Bot):
    await bot.add_cog(StandingsCog(bot))
