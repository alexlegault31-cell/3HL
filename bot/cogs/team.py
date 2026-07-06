
"""Team setup (/team create, /team link-club) and team stat/history/card
lookups."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.database import get_session
from bot.graphics.team_card import render_team_card
from bot.models import Game, Team, TeamSeason
from bot.services.leaders_service import goals_leaders, points_leaders
from bot.services.season_service import SeasonNotFound, resolve_season
from bot.utils.checks import commissioner_only
from bot.utils.embeds import error_embed, info_embed, success_embed


class TeamCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    team_group = app_commands.Group(name="team", description="Team management & stats")

    # ------------------------------------------------------------------
    # Commissioner setup
    # ------------------------------------------------------------------

    @team_group.command(name="create", description="Create a new league team")
    @app_commands.describe(name="Team name, e.g. Italy", abbreviation="3-4 letter abbreviation")
    @commissioner_only()
    async def create(self, interaction: discord.Interaction, name: str, abbreviation: str | None = None):
        async with get_session() as session:
            existing = await session.scalar(select(Team).where(Team.name == name))
            if existing:
                await interaction.response.send_message(embed=error_embed("Team exists", f"**{name}** already exists."), ephemeral=True)
                return

            team = Team(name=name, abbreviation=abbreviation)
            session.add(team)
            await session.flush()

            try:
                season = await resolve_season(session, None)
                session.add(TeamSeason(team_id=team.id, season_id=season.id))
            except SeasonNotFound:
                pass  # commissioner can link the season later; team itself is created

        await interaction.response.send_message(embed=success_embed("Team created", f"**{name}** has been added to the league."))

    @team_group.command(name="link-club", description="Link a team's EASHL Club ID for a season")
    @app_commands.describe(team="Team name", club_id="EASHL Club ID", season="Season number (defaults to active)")
    @commissioner_only()
    async def link_club(self, interaction: discord.Interaction, team: str, club_id: int, season: int | None = None):
        async with get_session() as session:
            t = await session.scalar(select(Team).where(Team.name.ilike(team)))
            if not t:
                await interaction.response.send_message(embed=error_embed("Unknown team", f"No team named **{team}**."), ephemeral=True)
                return
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            ts = await session.scalar(
                select(TeamSeason).where(TeamSeason.team_id == t.id, TeamSeason.season_id == s.id)
            )
            if ts is None:
                ts = TeamSeason(team_id=t.id, season_id=s.id)
                session.add(ts)
            ts.club_id = club_id

        await interaction.response.send_message(
            embed=success_embed("Club linked", f"**{team}** is now linked to Club ID `{club_id}` for {s.name}.")
        )

    # ------------------------------------------------------------------
    # Stats / lookups
    # ------------------------------------------------------------------

    @team_group.command(name="stats", description="View a team's record for a season")
    @app_commands.describe(team="Team name", season="Season number (defaults to active)")
    async def stats(self, interaction: discord.Interaction, team: str, season: int | None = None):
        async with get_session() as session:
            t = await session.scalar(select(Team).where(Team.name.ilike(team)))
            if not t:
                await interaction.response.send_message(embed=error_embed("Unknown team", f"No team named **{team}**."), ephemeral=True)
                return
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return
            ts = await session.scalar(select(TeamSeason).where(TeamSeason.team_id == t.id, TeamSeason.season_id == s.id))
            if not ts:
                await interaction.response.send_message(embed=info_embed("No record", f"{t.name} has no record for {s.name}."))
                return

            embed = info_embed(f"{t.name} — {s.name}")
            embed.add_field(name="Record", value=f"{ts.wins}-{ts.losses}-{ts.ot_losses}", inline=True)
            embed.add_field(name="Points", value=str(ts.points), inline=True)
            embed.add_field(name="Streak", value=f"{ts.streak_type or '-'}{ts.streak_count or ''}", inline=True)
            embed.add_field(name="GF", value=str(ts.goals_for), inline=True)
            embed.add_field(name="GA", value=str(ts.goals_against), inline=True)
            embed.add_field(name="Diff", value=str(ts.goal_diff), inline=True)
            if ts.club_id:
                embed.set_footer(text=f"Club ID: {ts.club_id}")
        await interaction.response.send_message(embed=embed)

    @team_group.command(name="history", description="View a team's match history for a season")
    @app_commands.describe(team="Team name", season="Season number (defaults to active)")
    async def history(self, interaction: discord.Interaction, team: str, season: int | None = None):
        async with get_session() as session:
            t = await session.scalar(select(Team).where(Team.name.ilike(team)))
            if not t:
                await interaction.response.send_message(embed=error_embed("Unknown team", f"No team named **{team}**."), ephemeral=True)
                return
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            stmt = (
                select(Game)
                .where(Game.season_id == s.id, (Game.home_team_id == t.id) | (Game.away_team_id == t.id))
                .order_by(Game.played_at.desc())
                .limit(15)
            )
            games = (await session.execute(stmt)).scalars().all()
            if not games:
                await interaction.response.send_message(embed=info_embed("No games", f"No games played yet for {t.name} in {s.name}."))
                return

            lines = []
            for g in games:
                home = await session.get(Team, g.home_team_id)
                away = await session.get(Team, g.away_team_id)
                tag = " (FFW)" if g.is_forfeit else (" (OT)" if g.went_to_overtime else "")
                lines.append(f"{home.name} {g.home_score} - {g.away_score} {away.name}{tag}")

        await interaction.response.send_message(embed=info_embed(f"{t.name} — Recent Games ({s.name})", "\n".join(lines)))

    @team_group.command(name="card", description="Generate a team profile graphic")
    @app_commands.describe(team="Team name", season="Season number (defaults to active)")
    async def card(self, interaction: discord.Interaction, team: str, season: int | None = None):
        await interaction.response.defer()
        async with get_session() as session:
            t = await session.scalar(select(Team).where(Team.name.ilike(team)))
            if not t:
                await interaction.followup.send(embed=error_embed("Unknown team", f"No team named **{team}**."))
                return
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.followup.send(embed=error_embed("Season error", str(e)))
                return
            ts = await session.scalar(select(TeamSeason).where(TeamSeason.team_id == t.id, TeamSeason.season_id == s.id))
            if not ts:
                await interaction.followup.send(embed=info_embed("No record", f"{t.name} has no record for {s.name}."))
                return

            top_scorers = await goals_leaders(session, s.id, limit=50)
            top_pts = await points_leaders(session, s.id, limit=50)
            team_top_scorer = next((r for r in top_scorers if r.team and r.team.id == t.id), None)
            team_top_pts = next((r for r in top_pts if r.team and r.team.id == t.id), None)

            lines = []
            if team_top_pts:
                lines.append(f"{team_top_pts.player.gamertag} — {team_top_pts.value} pts")
            if team_top_scorer and (not team_top_pts or team_top_scorer.player.id != team_top_pts.player.id):
                lines.append(f"{team_top_scorer.player.gamertag} — {team_top_scorer.value} goals")

            path = render_team_card(t, ts, s.name, lines)

        await interaction.followup.send(file=discord.File(path))


async def setup(bot: commands.Bot):
    await bot.add_cog(TeamCog(bot))

