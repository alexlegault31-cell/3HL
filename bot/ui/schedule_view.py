"""Persistent 'My Schedule' button for the schedule channel. Persistent
(not a normal timed-out view) so it keeps working across bot restarts --
this requires re-registering it in bot/main.py's setup_hook, see the
note there.

Clicking it looks up the user's linked player, finds their CURRENT
team for the active season (same team-tracking used everywhere else --
auto-updates the moment they play for a new team), and sends them an
ephemeral (only-they-can-see) schedule graphic filtered to just their
team's games.
"""
from __future__ import annotations

import discord
from sqlalchemy import or_, select

from bot.database import get_session
from bot.graphics.schedule_graphic import render_schedule
from bot.models import PlayerSeason, ScheduleGame, Team, User
from bot.services.league_settings import get_league_background_url, get_league_logo_url
from bot.services.season_service import SeasonNotFound, get_active_season
from bot.utils.embeds import error_embed, info_embed

MY_SCHEDULE_BUTTON_CUSTOM_ID = "nehl_my_schedule_button"


class ScheduleButtonView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)  # persistent -- must be re-registered on bot startup, see main.py

    @discord.ui.button(label="My Schedule", style=discord.ButtonStyle.primary, custom_id=MY_SCHEDULE_BUTTON_CUSTOM_ID, emoji="📅")
    async def my_schedule_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            user = await session.scalar(select(User).where(User.discord_id == interaction.user.id))
            if user is None or user.player_id is None:
                await interaction.followup.send(
                    embed=error_embed("Not linked", "Link your EA account first with `/league player link`, then try again."),
                    ephemeral=True,
                )
                return

            try:
                season = await get_active_season(session)
            except SeasonNotFound as e:
                await interaction.followup.send(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            ps = await session.scalar(
                select(PlayerSeason).where(PlayerSeason.player_id == user.player_id, PlayerSeason.season_id == season.id)
            )
            if ps is None or ps.team_id is None:
                await interaction.followup.send(
                    embed=info_embed("No team yet", "You haven't played a game this season yet, so you're not on a team yet."),
                    ephemeral=True,
                )
                return

            games = (
                await session.execute(
                    select(ScheduleGame)
                    .where(
                        ScheduleGame.season_id == season.id,
                        or_(ScheduleGame.home_team_id == ps.team_id, ScheduleGame.away_team_id == ps.team_id),
                    )
                    .order_by(ScheduleGame.week, ScheduleGame.game_number)
                )
            ).scalars().all()

            if not games:
                await interaction.followup.send(embed=info_embed("No games", "No games scheduled for your team yet."), ephemeral=True)
                return

            team = await session.get(Team, ps.team_id)
            all_team_ids = {t_id for g in games for t_id in (g.home_team_id, g.away_team_id)}
            teams_by_id = {t_id: await session.get(Team, t_id) for t_id in all_team_ids}
            league_logo_url = await get_league_logo_url(session, interaction.guild_id)
            background_url = await get_league_background_url(session, interaction.guild_id)

            paths = await render_schedule(f"{team.name.upper()} SCHEDULE", season.name, games, teams_by_id, league_logo_url, background_url)

        for i in range(0, len(paths), 10):
            chunk = paths[i : i + 10]
            await interaction.followup.send(files=[discord.File(p) for p in chunk], ephemeral=True)
