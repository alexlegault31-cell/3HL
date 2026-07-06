
################################################################
FILE PATH TO TYPE ON GITHUB: bot/cogs/leaders.py
################################################################
"""`/leaders goals|assists|points|goalie`"""
from __future__ import annotations

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from bot.database import get_session
from bot.graphics.team_card import render_leaders_board
from bot.services.leaders_service import assists_leaders, goalie_leaders, goals_leaders, points_leaders
from bot.services.season_service import SeasonNotFound, resolve_season
from bot.utils.embeds import error_embed, info_embed

CATEGORY_FUNCS = {
    "goals": (goals_leaders, "Goals Leaders"),
    "assists": (assists_leaders, "Assists Leaders"),
    "points": (points_leaders, "Points Leaders"),
    "goalie": (goalie_leaders, "Goalie Leaders (SV%)"),
}


class LeadersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="leaders", description="View league stat leaders")
    @app_commands.describe(category="Stat category", season="Season number (defaults to active)", graphic="Post as a graphic instead of text")
    async def leaders(
        self,
        interaction: discord.Interaction,
        category: Literal["goals", "assists", "points", "goalie"],
        season: int | None = None,
        graphic: bool = False,
    ):
        await interaction.response.defer()
        func, title = CATEGORY_FUNCS[category]

        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.followup.send(embed=error_embed("Season error", str(e)))
                return

            rows = await func(session, s.id, limit=10)
            if not rows:
                await interaction.followup.send(embed=info_embed("No data", f"No {category} data for {s.name} yet."))
                return

            if graphic:
                path = render_leaders_board(title, s.name, rows)
                await interaction.followup.send(file=discord.File(path))
                return

            lines = [f"`{r.rank:>2}` **{r.player.gamertag}**" + (f" ({r.team.name})" if r.team else "") + f" — {r.value} {('· ' + r.secondary) if r.secondary else ''}" for r in rows]

        await interaction.followup.send(embed=info_embed(f"{title} — {s.name}", "\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(LeadersCog(bot))

===== END OF FILE, COPY UP TO HERE =====
