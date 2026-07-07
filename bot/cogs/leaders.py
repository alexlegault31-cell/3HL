"""`/leaders <category>` -- always returns a graphic on success, matching
the "graphics, not text" preference. Categories now cover the full range
of stats EA's API provides, not just goals/assists/points."""
from __future__ import annotations

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from bot.database import get_session
from bot.graphics.team_card import render_leaders_board
from bot.services.leaders_service import (
    assists_leaders,
    blocked_shots_leaders,
    faceoff_pct_leaders,
    goalie_leaders,
    goals_leaders,
    hits_leaders,
    interceptions_leaders,
    pim_leaders,
    points_leaders,
    shutouts_leaders,
    takeaways_leaders,
)
from bot.services.season_service import SeasonNotFound, resolve_season
from bot.utils.embeds import error_embed, info_embed

CATEGORY_FUNCS = {
    "goals": (goals_leaders, "Goals Leaders"),
    "assists": (assists_leaders, "Assists Leaders"),
    "points": (points_leaders, "Points Leaders"),
    "hits": (hits_leaders, "Hits Leaders"),
    "pim": (pim_leaders, "Penalty Minutes Leaders"),
    "faceoff_pct": (faceoff_pct_leaders, "Faceoff % Leaders"),
    "takeaways": (takeaways_leaders, "Takeaways Leaders"),
    "interceptions": (interceptions_leaders, "Interceptions Leaders"),
    "blocked_shots": (blocked_shots_leaders, "Blocked Shots Leaders"),
    "goalie": (goalie_leaders, "Goalie Leaders (SV%)"),
    "shutouts": (shutouts_leaders, "Shutouts Leaders"),
}

CategoryLiteral = Literal[
    "goals", "assists", "points", "hits", "pim", "faceoff_pct", "takeaways", "interceptions", "blocked_shots", "goalie", "shutouts"
]


class LeadersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="leaders", description="View league stat leaders")
    @app_commands.describe(category="Stat category", season="Season number (defaults to active)")
    async def leaders(
        self,
        interaction: discord.Interaction,
        category: CategoryLiteral,
        season: int | None = None,
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

            path = render_leaders_board(title, s.name, rows)

        await interaction.followup.send(file=discord.File(path))


async def setup(bot: commands.Bot):
    await bot.add_cog(LeadersCog(bot))
