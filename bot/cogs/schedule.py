################################################################
FILE PATH TO TYPE ON GITHUB: bot/cogs/schedule.py
################################################################
"""Schedule system. The schedule is the source of truth: ScheduleGame rows
are created ahead of time (by a commissioner) and only transition to
"played" once /entergame successfully imports a result for them."""
from __future__ import annotations

import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.database import get_session
from bot.models import ScheduleGame, Team
from bot.models.schedule import ScheduleStatus
from bot.services.season_service import SeasonNotFound, resolve_season
from bot.utils.checks import commissioner_only
from bot.utils.embeds import error_embed, info_embed, success_embed


class ScheduleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    schedule_group = app_commands.Group(name="schedule", description="League schedule")

    @schedule_group.command(name="add", description="Add a game to the schedule")
    @app_commands.describe(
        game_number="Unique game number for this season, used by /entergame",
        home_team="Home team name",
        away_team="Away team name",
        week="Week number",
        season="Season number (defaults to active)",
    )
    @commissioner_only()
    async def add(
        self,
        interaction: discord.Interaction,
        game_number: int,
        home_team: str,
        away_team: str,
        week: int | None = None,
        season: int | None = None,
    ):
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            home = await session.scalar(select(Team).where(Team.name.ilike(home_team)))
            away = await session.scalar(select(Team).where(Team.name.ilike(away_team)))
            if not home or not away:
                await interaction.response.send_message(embed=error_embed("Unknown team", "Both teams must already exist (`/team create`)."), ephemeral=True)
                return

            existing = await session.scalar(
                select(ScheduleGame).where(ScheduleGame.season_id == s.id, ScheduleGame.game_number == game_number)
            )
            if existing:
                await interaction.response.send_message(embed=error_embed("Already scheduled", f"Game #{game_number} already exists for {s.name}."), ephemeral=True)
                return

            session.add(
                ScheduleGame(
                    season_id=s.id,
                    game_number=game_number,
                    week=week,
                    home_team_id=home.id,
                    away_team_id=away.id,
                )
            )

        await interaction.response.send_message(
            embed=success_embed("Scheduled", f"Game #{game_number}: **{home_team}** vs **{away_team}** added to {s.name}.")
        )

    @schedule_group.command(name="view", description="View the full schedule for a season")
    @app_commands.describe(season="Season number (defaults to active)")
    async def view(self, interaction: discord.Interaction, season: int | None = None):
        await self._send_schedule(interaction, season=season, week=None, status=None)

    @schedule_group.command(name="week", description="View the schedule for a specific week")
    @app_commands.describe(week="Week number", season="Season number (defaults to active)")
    async def week(self, interaction: discord.Interaction, week: int, season: int | None = None):
        await self._send_schedule(interaction, season=season, week=week, status=None)

    @schedule_group.command(name="pending", description="View games not yet played")
    @app_commands.describe(season="Season number (defaults to active)")
    async def pending(self, interaction: discord.Interaction, season: int | None = None):
        await self._send_schedule(interaction, season=season, week=None, status=ScheduleStatus.SCHEDULED)

    async def _send_schedule(self, interaction: discord.Interaction, *, season: int | None, week: int | None, status: ScheduleStatus | None):
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            stmt = select(ScheduleGame).where(ScheduleGame.season_id == s.id)
            if week is not None:
                stmt = stmt.where(ScheduleGame.week == week)
            if status is not None:
                stmt = stmt.where(ScheduleGame.status == status)
            stmt = stmt.order_by(ScheduleGame.game_number)

            games = (await session.execute(stmt)).scalars().all()
            if not games:
                await interaction.response.send_message(embed=info_embed("No games", "No matching games found."))
                return

            lines = []
            for g in games:
                home = await session.get(Team, g.home_team_id)
                away = await session.get(Team, g.away_team_id)
                status_icon = {
                    ScheduleStatus.SCHEDULED: "🕒",
                    ScheduleStatus.PLAYED: "✅",
                    ScheduleStatus.FORFEITED: "🚫",
                    ScheduleStatus.POSTPONED: "⏸️",
                    ScheduleStatus.CANCELLED: "❌",
                }[g.status]
                week_str = f"Wk{g.week} " if g.week else ""
                lines.append(f"{status_icon} `#{g.game_number}` {week_str}{home.name} vs {away.name}")

            chunks = ["\n".join(lines[i : i + 25]) for i in range(0, len(lines), 25)]

        title = f"Schedule — {s.name}"
        await interaction.response.send_message(embed=info_embed(title, chunks[0]))
        for chunk in chunks[1:]:
            await interaction.followup.send(embed=info_embed(title, chunk))


async def setup(bot: commands.Bot):
    await bot.add_cog(ScheduleCog(bot))

===== END OF FILE, COPY UP TO HERE =====
