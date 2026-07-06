
"""Awards: commissioner-defined categories (MVP, Best Goalie, Best
Defenseman, Rookie, ...) handed out per-season."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.database import get_session
from bot.models import Award, AwardWinner, Player, Team
from bot.services.season_service import SeasonNotFound, resolve_season
from bot.utils.checks import commissioner_only
from bot.utils.embeds import error_embed, info_embed, success_embed


class AwardsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    award_group = app_commands.Group(name="award", description="League awards")

    @award_group.command(name="create", description="Create a new award category")
    @app_commands.describe(key="Short key, e.g. mvp", display_name="Full name, e.g. Most Valuable Player")
    @commissioner_only()
    async def create(self, interaction: discord.Interaction, key: str, display_name: str):
        async with get_session() as session:
            existing = await session.scalar(select(Award).where(Award.key == key))
            if existing:
                await interaction.response.send_message(embed=error_embed("Exists", f"Award `{key}` already exists."), ephemeral=True)
                return
            session.add(Award(key=key, display_name=display_name))
        await interaction.response.send_message(embed=success_embed("Award created", f"**{display_name}** (`{key}`) added."))

    @award_group.command(name="give", description="Award a player for a season")
    @app_commands.describe(key="Award key", gamertag="Player gamertag", season="Season number (defaults to active)", note="Optional note")
    @commissioner_only()
    async def give(self, interaction: discord.Interaction, key: str, gamertag: str, season: int | None = None, note: str | None = None):
        async with get_session() as session:
            award = await session.scalar(select(Award).where(Award.key == key))
            if not award:
                await interaction.response.send_message(embed=error_embed("Unknown award", f"No award with key `{key}`."), ephemeral=True)
                return
            player = await session.scalar(select(Player).where(Player.gamertag.ilike(gamertag)))
            if not player:
                await interaction.response.send_message(embed=error_embed("Unknown player", f"No player `{gamertag}`."), ephemeral=True)
                return
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            session.add(
                AwardWinner(
                    award_id=award.id,
                    season_id=s.id,
                    player_id=player.id,
                    note=note,
                    awarded_by_discord_id=interaction.user.id,
                )
            )

        await interaction.response.send_message(
            embed=success_embed("Award given", f"🏆 **{player.gamertag}** wins **{award.display_name}** — {s.name}")
        )

    @award_group.command(name="list", description="View award winners for a season")
    @app_commands.describe(season="Season number (defaults to active)")
    async def list_(self, interaction: discord.Interaction, season: int | None = None):
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            stmt = select(AwardWinner).where(AwardWinner.season_id == s.id)
            winners = (await session.execute(stmt)).scalars().all()
            if not winners:
                await interaction.response.send_message(embed=info_embed("No awards yet", f"No awards have been given for {s.name}."))
                return

            lines = []
            for w in winners:
                award = await session.get(Award, w.award_id)
                player = await session.get(Player, w.player_id)
                lines.append(f"🏆 **{award.display_name}** — {player.gamertag}")

        await interaction.response.send_message(embed=info_embed(f"Awards — {s.name}", "\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(AwardsCog(bot))

