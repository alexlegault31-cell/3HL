
################################################################
FILE PATH TO TYPE ON GITHUB: bot/cogs/player.py
################################################################
"""Player <-> Discord account linking and stat lookups."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.database import get_session
from bot.graphics.player_card import render_player_card
from bot.models import Player, PlayerGameStat, PlayerSeason, Team, User
from bot.services.season_service import SeasonNotFound, resolve_season
from bot.utils.embeds import error_embed, info_embed, success_embed


class PlayerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    player_group = app_commands.Group(name="player", description="Player linking & stats")

    @player_group.command(name="link", description="Link your Discord account to your NHL gamertag")
    @app_commands.describe(gamertag="Your exact PSN/Xbox/EA gamertag as it appears in-game")
    async def link(self, interaction: discord.Interaction, gamertag: str):
        async with get_session() as session:
            user = await session.scalar(select(User).where(User.discord_id == interaction.user.id))
            if user is None:
                user = User(discord_id=interaction.user.id, discord_username=str(interaction.user))
                session.add(user)
                await session.flush()

            player = await session.scalar(select(Player).where(Player.gamertag.ilike(gamertag)))
            if player is None:
                player = Player(gamertag=gamertag)
                session.add(player)
                await session.flush()

            other_user = await session.scalar(select(User).where(User.player_id == player.id, User.id != user.id))
            if other_user is not None:
                await interaction.response.send_message(
                    embed=error_embed("Already linked", f"`{gamertag}` is already linked to another Discord account."),
                    ephemeral=True,
                )
                return

            user.player_id = player.id

        await interaction.response.send_message(
            embed=success_embed("Account linked", f"Your Discord account is now linked to **{gamertag}**."),
            ephemeral=True,
        )

    @player_group.command(name="stats", description="View a player's season stats")
    @app_commands.describe(gamertag="Player gamertag (defaults to your linked account)", season="Season number (defaults to active)")
    async def stats(self, interaction: discord.Interaction, gamertag: str | None = None, season: int | None = None):
        async with get_session() as session:
            player = await self._resolve_player(session, interaction, gamertag)
            if player is None:
                await interaction.response.send_message(
                    embed=error_embed("No player found", "Provide a gamertag or link your account with `/player link`."),
                    ephemeral=True,
                )
                return
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            ps = await session.scalar(select(PlayerSeason).where(PlayerSeason.player_id == player.id, PlayerSeason.season_id == s.id))
            if ps is None:
                await interaction.response.send_message(embed=info_embed("No stats", f"No stats for {player.gamertag} in {s.name}."))
                return

            embed = info_embed(f"{player.gamertag} — {s.name}")
            if player.is_goalie:
                embed.add_field(name="Record", value=f"{ps.wins}-{ps.losses}-{ps.ot_losses}", inline=True)
                embed.add_field(name="GAA", value=f"{ps.gaa:.2f}", inline=True)
                embed.add_field(name="SV%", value=f"{ps.save_pct:.3f}", inline=True)
                embed.add_field(name="Shutouts", value=str(ps.shutouts), inline=True)
                embed.add_field(name="Saves", value=str(ps.saves), inline=True)
                embed.add_field(name="GP", value=str(ps.games_played), inline=True)
            else:
                embed.add_field(name="GP", value=str(ps.games_played), inline=True)
                embed.add_field(name="G", value=str(ps.goals), inline=True)
                embed.add_field(name="A", value=str(ps.assists), inline=True)
                embed.add_field(name="PTS", value=str(ps.points), inline=True)
                embed.add_field(name="+/-", value=str(ps.plus_minus), inline=True)
                embed.add_field(name="PIM", value=str(ps.pim), inline=True)

        await interaction.response.send_message(embed=embed)

    @player_group.command(name="gamelog", description="View a player's recent per-game stat lines")
    @app_commands.describe(gamertag="Player gamertag (defaults to your linked account)", season="Season number (defaults to active)")
    async def gamelog(self, interaction: discord.Interaction, gamertag: str | None = None, season: int | None = None):
        async with get_session() as session:
            player = await self._resolve_player(session, interaction, gamertag)
            if player is None:
                await interaction.response.send_message(
                    embed=error_embed("No player found", "Provide a gamertag or link your account with `/player link`."),
                    ephemeral=True,
                )
                return
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            stmt = (
                select(PlayerGameStat)
                .where(PlayerGameStat.player_id == player.id, PlayerGameStat.season_id == s.id)
                .order_by(PlayerGameStat.id.desc())
                .limit(10)
            )
            lines = (await session.execute(stmt)).scalars().all()
            if not lines:
                await interaction.response.send_message(embed=info_embed("No games", f"No game log for {player.gamertag} in {s.name}."))
                return
            text = "\n".join(f"G:{l.goals} A:{l.assists} PTS:{l.points} +/-:{l.plus_minus} HIT:{l.hits} PIM:{l.pim}" for l in lines)

        await interaction.response.send_message(embed=info_embed(f"{player.gamertag} — Game Log ({s.name})", text))

    @player_group.command(name="card", description="Generate a player profile graphic")
    @app_commands.describe(gamertag="Player gamertag (defaults to your linked account)", season="Season number (defaults to active)")
    async def card(self, interaction: discord.Interaction, gamertag: str | None = None, season: int | None = None):
        await interaction.response.defer()
        async with get_session() as session:
            player = await self._resolve_player(session, interaction, gamertag)
            if player is None:
                await interaction.followup.send(embed=error_embed("No player found", "Provide a gamertag or link your account with `/player link`."))
                return
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.followup.send(embed=error_embed("Season error", str(e)))
                return
            ps = await session.scalar(select(PlayerSeason).where(PlayerSeason.player_id == player.id, PlayerSeason.season_id == s.id))
            if ps is None:
                await interaction.followup.send(embed=info_embed("No stats", f"No stats for {player.gamertag} in {s.name}."))
                return
            team = await session.get(Team, ps.team_id) if ps.team_id else None
            path = render_player_card(player, ps, team, s.name)

        await interaction.followup.send(file=discord.File(path))

    @staticmethod
    async def _resolve_player(session, interaction: discord.Interaction, gamertag: str | None) -> Player | None:
        if gamertag:
            return await session.scalar(select(Player).where(Player.gamertag.ilike(gamertag)))
        user = await session.scalar(select(User).where(User.discord_id == interaction.user.id))
        if user and user.player_id:
            return await session.get(Player, user.player_id)
        return None


async def setup(bot: commands.Bot):
    await bot.add_cog(PlayerCog(bot))

===== END OF FILE, COPY UP TO HERE =====
