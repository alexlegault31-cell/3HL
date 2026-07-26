"""Persistent 'Team Schedule' button for the schedule channel. Persistent
(not a normal timed-out view) so it keeps working across bot restarts --
this requires re-registering it in bot/main.py's setup_hook, see the
note there.

Clicking it shows a dropdown of every active club; picking one sends an
ephemeral (only-the-clicker-can-see) schedule graphic for that team --
anyone's schedule, not just your own.
"""
from __future__ import annotations

import discord
from sqlalchemy import or_, select

from bot.database import get_session
from bot.graphics.schedule_graphic import render_schedule
from bot.models import ScheduleGame, Team
from bot.services.league_settings import get_league_background_url, get_league_logo_url
from bot.services.season_service import SeasonNotFound, get_active_season
from bot.utils.embeds import error_embed, info_embed

TEAM_SCHEDULE_BUTTON_CUSTOM_ID = "nehl_team_schedule_button"


class ScheduleButtonView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)  # persistent -- must be re-registered on bot startup, see main.py

    @discord.ui.button(label="Team Schedule", style=discord.ButtonStyle.primary, custom_id=TEAM_SCHEDULE_BUTTON_CUSTOM_ID, emoji="📅")
    async def team_schedule_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            try:
                season = await get_active_season(session)
            except SeasonNotFound as e:
                await interaction.followup.send(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            teams = (await session.execute(select(Team).where(Team.is_active.is_(True)).order_by(Team.name))).scalars().all()
            if not teams:
                await interaction.followup.send(embed=info_embed("No clubs", "No clubs have been added yet."), ephemeral=True)
                return

        view = _TeamPickerView(teams, season.id, season.name)
        await interaction.followup.send("Which team's schedule would you like to see?", view=view, ephemeral=True)


class _TeamPickerView(discord.ui.View):
    def __init__(self, teams: list[Team], season_id: int, season_name: str) -> None:
        super().__init__(timeout=120)
        self._season_id = season_id
        self._season_name = season_name

        select = discord.ui.Select(
            placeholder="Choose a team...",
            options=[discord.SelectOption(label=t.name, value=str(t.id)) for t in teams[:25]],
        )
        select.callback = self._callback
        self._select = select
        self.add_item(select)

    async def _callback(self, interaction: discord.Interaction) -> None:
        team_id = int(self._select.values[0])
        await interaction.response.defer(ephemeral=True)

        async with get_session() as session:
            team = await session.get(Team, team_id)
            games = (
                await session.execute(
                    select(ScheduleGame)
                    .where(
                        ScheduleGame.season_id == self._season_id,
                        or_(ScheduleGame.home_team_id == team_id, ScheduleGame.away_team_id == team_id),
                    )
                    .order_by(ScheduleGame.week, ScheduleGame.game_number)
                )
            ).scalars().all()

            if not games:
                await interaction.followup.send(embed=info_embed("No games", f"No games scheduled for **{team.name}** yet."), ephemeral=True)
                return

            all_team_ids = {t_id for g in games for t_id in (g.home_team_id, g.away_team_id)}
            teams_by_id = {t_id: await session.get(Team, t_id) for t_id in all_team_ids}
            league_logo_url = await get_league_logo_url(session, interaction.guild_id)
            background_url = await get_league_background_url(session, interaction.guild_id)

            paths = await render_schedule(f"{team.name.upper()} SCHEDULE", self._season_name, games, teams_by_id, league_logo_url, background_url)

        for i in range(0, len(paths), 10):
            chunk = paths[i : i + 10]
            await interaction.followup.send(files=[discord.File(p) for p in chunk], ephemeral=True)
