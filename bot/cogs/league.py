"""
Consolidated `/league` command tree: `/league season`, `/league club`,
`/league player`, `/league list`, `/league admin`, `/league refresh`,
`/league schedule`, plus top-level `/league postpone-game`,
`/league admin generate-playoffs`, `/league admin advance-round`.
"""
from __future__ import annotations

import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.cogs.channel_updater import refresh_all_channels
from bot.config import settings
from bot.database import get_session
from bot.graphics.combined_leaders_board import render_combined_leaders_board
from bot.graphics.game_result_graphic import render_game_result
from bot.graphics.player_card import render_player_card
from bot.graphics.playoff_bracket import render_playoff_bracket
from bot.graphics.standings_graphic import render_standings
from bot.graphics.team_card import render_team_card
from bot.models import (
    Forfeit,
    Game,
    GuildSetting,
    Player,
    PlayerSeason,
    PlayerTeamLink,
    ScheduleGame,
    Season,
    StandingsEntry,
    Team,
    TeamSeason,
    User,
)
from bot.models.schedule import ScheduleStatus
from bot.services.game_log_service import get_goalie_game_log, get_skater_game_log, get_team_recent_results
from bot.services.roster_service import get_team_roster
from bot.services.unlinked_players_service import find_unlinked_players_in_game
from bot.services.leaders_service import (
    assists_leaders,
    blocked_shots_leaders,
    faceoff_pct_leaders,
    gaa_leaders,
    goalie_leaders,
    goals_leaders,
    hits_leaders,
    interceptions_leaders,
    pim_leaders,
    points_leaders,
    shutouts_leaders,
    takeaways_leaders,
)
from bot.services.league_settings import get_league_background_url, get_league_logo_url, set_league_background_url
from bot.services.playoff_service import PlayoffError, advance_round, generate_bracket, get_bracket, record_series_result
from bot.services.recap_generator import RecapContext, format_top_performers, generate_recap
from bot.services.schedule_generator import generate_round_robin
from bot.services.season_service import SeasonNotFound, resolve_season, set_active_season
from bot.services.stat_importer import ImportError_, apply_team_season_delta, find_pending_schedule_for_matchup, import_game, reverse_game
from bot.services.standings_service import recompute_standings
from bot.utils.checks import commissioner_only, gm_only
from bot.utils.embeds import error_embed, info_embed, success_embed


async def team_name_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Shared autocomplete for every club-name text field -- Discord shows
    this as a live filtered dropdown as the user types, built from
    whatever clubs actually exist in the league rather than a fixed list.
    Module-level (not a class method) since it needs to be fully defined
    before any command in the class below references it in a decorator."""
    async with get_session() as session:
        stmt = select(Team.name).where(Team.is_active.is_(True))
        if current:
            stmt = stmt.where(Team.name.ilike(f"%{current}%"))
        stmt = stmt.order_by(Team.name).limit(25)
        names = (await session.execute(stmt)).scalars().all()
    return [app_commands.Choice(name=n, value=n) for n in names]


async def player_gamertag_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Shared autocomplete for existing-player gamertag text fields (NOT
    used for /league player add, since that command is for typing a
    brand-new player's name)."""
    async with get_session() as session:
        stmt = select(Player.gamertag)
        if current:
            stmt = stmt.where(Player.gamertag.ilike(f"%{current}%"))
        stmt = stmt.order_by(Player.gamertag).limit(25)
        names = (await session.execute(stmt)).scalars().all()
    return [app_commands.Choice(name=n, value=n) for n in names]


class LeagueCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    league_group = app_commands.Group(name="league", description="League management")

    season_group = app_commands.Group(name="season", description="Season management", parent=league_group)
    club_group = app_commands.Group(name="club", description="Club/team management", parent=league_group)
    player_group = app_commands.Group(name="player", description="Player management", parent=league_group)
    list_group = app_commands.Group(name="list", description="League directories & leaders", parent=league_group)
    admin_group = app_commands.Group(name="admin", description="Commissioner administration", parent=league_group)
    refresh_group = app_commands.Group(name="refresh", description="Manually re-post league graphics", parent=league_group)
    schedule_group = app_commands.Group(name="schedule", description="League schedule", parent=league_group)

    # ==================================================================
    # /league season
    # ==================================================================

    @season_group.command(name="create-new", description="Create a new league season")
    @app_commands.describe(number="Season number, e.g. 3", name="Display name, defaults to 'Season N'")
    @commissioner_only()
    async def season_create(self, interaction: discord.Interaction, number: int, name: str | None = None):
        async with get_session() as session:
            existing = await session.scalar(select(Season).where(Season.number == number))
            if existing:
                await interaction.response.send_message(embed=error_embed("Season exists", f"Season {number} already exists."), ephemeral=True)
                return
            season = Season(number=number, name=name or f"Season {number}")
            session.add(season)
        await interaction.response.send_message(embed=success_embed("Season created", f"**{season.name}** has been created."))

    @season_group.command(name="start", description="Activate a season as the current league season")
    @app_commands.describe(number="Season number to activate")
    @commissioner_only()
    async def season_start(self, interaction: discord.Interaction, number: int):
        async with get_session() as session:
            try:
                season = await set_active_season(session, number)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Not found", str(e)), ephemeral=True)
                return
        await interaction.response.send_message(embed=success_embed("Season started", f"**{season.name}** is now the active season."))

    @season_group.command(name="rename", description="Rename a season")
    @app_commands.describe(number="Season number", new_name="New display name")
    @commissioner_only()
    async def season_rename(self, interaction: discord.Interaction, number: int, new_name: str):
        async with get_session() as session:
            season = await session.scalar(select(Season).where(Season.number == number))
            if not season:
                await interaction.response.send_message(embed=error_embed("Not found", f"Season {number} doesn't exist."), ephemeral=True)
                return
            old_name = season.name
            season.name = new_name
        await interaction.response.send_message(embed=success_embed("Season renamed", f"**{old_name}** → **{new_name}**"))

    @season_group.command(name="settings", description="View or update season settings")
    @app_commands.describe(number="Season number (defaults to active)", playoffs_active="Set whether playoffs are active for this season")
    @commissioner_only()
    async def season_settings(self, interaction: discord.Interaction, number: int | None = None, playoffs_active: bool | None = None):
        async with get_session() as session:
            try:
                season = await resolve_season(session, number)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return
            if playoffs_active is not None:
                season.is_playoffs_active = playoffs_active
            embed = info_embed(
                f"Settings — {season.name}",
                f"Active: {'Yes' if season.is_active else 'No'}\n"
                f"Playoffs active: {'Yes' if season.is_playoffs_active else 'No'}\n"
                f"Start date: {season.start_date or '—'}\n"
                f"End date: {season.end_date or '—'}",
            )
        await interaction.response.send_message(embed=embed)

    # ==================================================================
    # /league club
    # ==================================================================

    @club_group.command(name="add", description="Add a new club to the league")
    @app_commands.describe(name="Club name, e.g. Italy", abbreviation="3-4 letter abbreviation")
    @commissioner_only()
    async def club_add(self, interaction: discord.Interaction, name: str, abbreviation: str | None = None):
        async with get_session() as session:
            existing = await session.scalar(select(Team).where(Team.name == name))
            if existing:
                await interaction.response.send_message(embed=error_embed("Club exists", f"**{name}** already exists."), ephemeral=True)
                return
            team = Team(name=name, abbreviation=abbreviation)
            session.add(team)
            await session.flush()
            try:
                season = await resolve_season(session, None)
                session.add(TeamSeason(team_id=team.id, season_id=season.id))
            except SeasonNotFound:
                pass
        await interaction.response.send_message(embed=success_embed("Club added", f"**{name}** has been added to the league."))

    @club_group.command(name="remove", description="Remove a club from the league (soft-delete, preserves history)")
    @app_commands.describe(name="Club name to remove")
    @app_commands.autocomplete(name=team_name_autocomplete)
    @commissioner_only()
    async def club_remove(self, interaction: discord.Interaction, name: str):
        async with get_session() as session:
            team = await session.scalar(select(Team).where(Team.name.ilike(name)))
            if not team:
                await interaction.response.send_message(embed=error_embed("Unknown club", f"No club named **{name}**."), ephemeral=True)
                return
            team.is_active = False
        await interaction.response.send_message(embed=success_embed("Club removed", f"**{name}** has been deactivated. Historical stats/games are preserved."))

    @club_group.command(name="swap", description="Change a club's linked EASHL Club ID")
    @app_commands.describe(name="Club name", new_club_id="New EASHL Club ID", season="Season number (defaults to active)")
    @app_commands.autocomplete(name=team_name_autocomplete)
    @commissioner_only()
    async def club_swap(self, interaction: discord.Interaction, name: str, new_club_id: int, season: int | None = None):
        async with get_session() as session:
            team = await session.scalar(select(Team).where(Team.name.ilike(name)))
            if not team:
                await interaction.response.send_message(embed=error_embed("Unknown club", f"No club named **{name}**."), ephemeral=True)
                return
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return
            ts = await session.scalar(select(TeamSeason).where(TeamSeason.team_id == team.id, TeamSeason.season_id == s.id))
            if ts is None:
                ts = TeamSeason(team_id=team.id, season_id=s.id)
                session.add(ts)
            old_id = ts.club_id
            ts.club_id = new_club_id
        await interaction.response.send_message(
            embed=success_embed("Club ID updated", f"**{name}** Club ID changed from `{old_id or '—'}` to `{new_club_id}` for {s.name}.")
        )

    @club_group.command(name="add-logo", description="Set a club's logo")
    @app_commands.describe(name="Club name", logo_url="Direct image URL for the logo")
    @app_commands.autocomplete(name=team_name_autocomplete)
    @commissioner_only()
    async def club_add_logo(self, interaction: discord.Interaction, name: str, logo_url: str):
        async with get_session() as session:
            team = await session.scalar(select(Team).where(Team.name.ilike(name)))
            if not team:
                await interaction.response.send_message(embed=error_embed("Unknown club", f"No club named **{name}**."), ephemeral=True)
                return
            team.logo_url = logo_url
        await interaction.response.send_message(embed=success_embed("Logo updated", f"Logo set for **{name}**."))

    @club_group.command(name="stats", description="View a club's record for a season")
    @app_commands.describe(name="Club name", season="Season number (defaults to active)")
    @app_commands.autocomplete(name=team_name_autocomplete)
    async def club_stats(self, interaction: discord.Interaction, name: str, season: int | None = None):
        await interaction.response.defer()
        async with get_session() as session:
            team = await session.scalar(select(Team).where(Team.name.ilike(name)))
            if not team:
                await interaction.followup.send(embed=error_embed("Unknown club", f"No club named **{name}**."))
                return
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.followup.send(embed=error_embed("Season error", str(e)))
                return

            ts = await session.scalar(select(TeamSeason).where(TeamSeason.team_id == team.id, TeamSeason.season_id == s.id))
            if ts is None:
                ts = TeamSeason(
                    team_id=team.id, season_id=s.id, club_id=None,
                    wins=0, losses=0, ot_losses=0, points=0,
                    goals_for=0, goals_against=0,
                    streak_type=None, streak_count=0, last_10=None,
                )

            top_scorers = await goals_leaders(session, s.id, limit=50)
            top_pts = await points_leaders(session, s.id, limit=50)
            team_top_pts = next((r for r in top_pts if r.team and r.team.id == team.id), None)
            team_top_scorer = next((r for r in top_scorers if r.team and r.team.id == team.id), None)
            lines = []
            if team_top_pts:
                lines.append(f"{team_top_pts.player.gamertag} — {team_top_pts.value} pts")
            if team_top_scorer and (not team_top_pts or team_top_scorer.player.id != team_top_pts.player.id):
                lines.append(f"{team_top_scorer.player.gamertag} — {team_top_scorer.value} goals")

            league_logo_url = await get_league_logo_url(session, interaction.guild_id)
            background_url = await get_league_background_url(session, interaction.guild_id)
            recent_results = await get_team_recent_results(session, team.id, s.id, limit=15)
            skaters, goalies = await get_team_roster(session, team.id, s.id)
            path = await render_team_card(team, ts, s.name, lines, league_logo_url, background_url, recent_results, skaters, goalies)
        await interaction.followup.send(file=discord.File(path))

    # ==================================================================
    # /league player
    # ==================================================================

    @player_group.command(name="add", description="Add a player to a club's roster")
    @app_commands.describe(gamertag="Player gamertag", club="Club name", season="Season number (defaults to active)")
    @app_commands.autocomplete(club=team_name_autocomplete)
    @gm_only()
    async def player_add(self, interaction: discord.Interaction, gamertag: str, club: str, season: int | None = None):
        async with get_session() as session:
            team = await session.scalar(select(Team).where(Team.name.ilike(club)))
            if not team:
                await interaction.response.send_message(embed=error_embed("Unknown club", f"No club named **{club}**."), ephemeral=True)
                return
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            player = await session.scalar(select(Player).where(Player.gamertag.ilike(gamertag)))
            if player is None:
                player = Player(gamertag=gamertag)
                session.add(player)
                await session.flush()

            link = await session.scalar(
                select(PlayerTeamLink).where(
                    PlayerTeamLink.player_id == player.id, PlayerTeamLink.season_id == s.id, PlayerTeamLink.team_id == team.id
                )
            )
            if link is None:
                session.add(PlayerTeamLink(player_id=player.id, team_id=team.id, season_id=s.id, is_current=True))

            ps = await session.scalar(select(PlayerSeason).where(PlayerSeason.player_id == player.id, PlayerSeason.season_id == s.id))
            if ps is None:
                session.add(PlayerSeason(player_id=player.id, season_id=s.id, team_id=team.id))
            else:
                ps.team_id = team.id

        await interaction.response.send_message(embed=success_embed("Player added", f"**{gamertag}** added to **{club}** for {s.name}."))

    @player_group.command(name="move", description="Move a player to a different club")
    @app_commands.describe(gamertag="Player gamertag", new_club="New club name", season="Season number (defaults to active)")
    @app_commands.autocomplete(gamertag=player_gamertag_autocomplete, new_club=team_name_autocomplete)
    @gm_only()
    async def player_move(self, interaction: discord.Interaction, gamertag: str, new_club: str, season: int | None = None):
        async with get_session() as session:
            player = await session.scalar(select(Player).where(Player.gamertag.ilike(gamertag)))
            if not player:
                await interaction.response.send_message(embed=error_embed("Unknown player", f"No player **{gamertag}**."), ephemeral=True)
                return
            team = await session.scalar(select(Team).where(Team.name.ilike(new_club)))
            if not team:
                await interaction.response.send_message(embed=error_embed("Unknown club", f"No club named **{new_club}**."), ephemeral=True)
                return
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            old_links = (
                await session.execute(
                    select(PlayerTeamLink).where(PlayerTeamLink.player_id == player.id, PlayerTeamLink.season_id == s.id)
                )
            ).scalars().all()
            for l in old_links:
                l.is_current = False

            session.add(PlayerTeamLink(player_id=player.id, team_id=team.id, season_id=s.id, is_current=True))

            ps = await session.scalar(select(PlayerSeason).where(PlayerSeason.player_id == player.id, PlayerSeason.season_id == s.id))
            if ps:
                ps.team_id = team.id

        await interaction.response.send_message(embed=success_embed("Player moved", f"**{gamertag}** moved to **{new_club}** for {s.name}."))

    @player_group.command(name="remove", description="Remove a player from their current club")
    @app_commands.describe(gamertag="Player gamertag", season="Season number (defaults to active)")
    @app_commands.autocomplete(gamertag=player_gamertag_autocomplete)
    @gm_only()
    async def player_remove(self, interaction: discord.Interaction, gamertag: str, season: int | None = None):
        async with get_session() as session:
            player = await session.scalar(select(Player).where(Player.gamertag.ilike(gamertag)))
            if not player:
                await interaction.response.send_message(embed=error_embed("Unknown player", f"No player **{gamertag}**."), ephemeral=True)
                return
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            links = (
                await session.execute(
                    select(PlayerTeamLink).where(PlayerTeamLink.player_id == player.id, PlayerTeamLink.season_id == s.id, PlayerTeamLink.is_current.is_(True))
                )
            ).scalars().all()
            for l in links:
                l.is_current = False

            ps = await session.scalar(select(PlayerSeason).where(PlayerSeason.player_id == player.id, PlayerSeason.season_id == s.id))
            if ps:
                ps.team_id = None

        await interaction.response.send_message(embed=success_embed("Player removed", f"**{gamertag}** removed from their club for {s.name}."))

    @player_group.command(name="stats", description="View a player's season stats card")
    @app_commands.describe(
        discord_user="Pick a Discord member (uses their linked EA gamertag) -- defaults to you",
        gamertag="Or type an EA gamertag directly, if they haven't linked their account",
        season="Season number (defaults to active)",
    )
    async def player_stats(
        self,
        interaction: discord.Interaction,
        discord_user: discord.Member | None = None,
        gamertag: str | None = None,
        season: int | None = None,
    ):
        await interaction.response.defer()
        async with get_session() as session:
            player = await self._resolve_player(session, interaction, gamertag, discord_user)
            if player is None:
                who = discord_user.mention if discord_user else "That account"
                await interaction.followup.send(
                    embed=error_embed(
                        "No player found",
                        f"{who} hasn't linked an EA gamertag yet -- use `/league player link` first, or provide a gamertag directly.",
                    )
                )
                return
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.followup.send(embed=error_embed("Season error", str(e)))
                return

            ps = await session.scalar(select(PlayerSeason).where(PlayerSeason.player_id == player.id, PlayerSeason.season_id == s.id))
            team = None
            if ps is None:
                ps = PlayerSeason(
                    player_id=player.id, season_id=s.id, team_id=None,
                    games_played=0, goals=0, assists=0, points=0, plus_minus=0,
                    hits=0, pim=0, shots=0, ppg=0,
                    faceoffs_won=0, faceoffs_lost=0, takeaways=0, interceptions=0,
                    blocked_shots=0, giveaways=0, pass_attempts=0, passes_completed=0,
                    wins=0, losses=0, ot_losses=0, shots_against=0, saves=0,
                    goals_against=0, shutouts=0, minutes_played=0.0,
                )
            else:
                team = await session.get(Team, ps.team_id) if ps.team_id else None

            if player.is_goalie:
                game_log = await get_goalie_game_log(session, player.id, s.id)
            else:
                game_log = await get_skater_game_log(session, player.id, s.id)

            league_logo_url = await get_league_logo_url(session, interaction.guild_id)
            background_url = await get_league_background_url(session, interaction.guild_id)
            path = await render_player_card(player, ps, team, s.name, league_logo_url, background_url, game_log)

        await interaction.followup.send(file=discord.File(path))

    @player_group.command(name="link", description="Link your Discord account to your EA gamertag")
    @app_commands.describe(gamertag="Your EA gamertag")
    async def player_link(self, interaction: discord.Interaction, gamertag: str):
        async with get_session() as session:
            player = await session.scalar(select(Player).where(Player.gamertag.ilike(gamertag)))
            if player is None:
                await interaction.response.send_message(
                    embed=error_embed(
                        "Unknown gamertag",
                        f"No player named **{gamertag}** exists yet -- they need to be added to a club first with `/league player add` before you can link to them.",
                    ),
                    ephemeral=True,
                )
                return

            existing_user = await session.scalar(select(User).where(User.discord_id == interaction.user.id))
            if existing_user is None:
                session.add(User(discord_id=interaction.user.id, player_id=player.id))
            else:
                existing_user.player_id = player.id

        await interaction.response.send_message(
            embed=success_embed("Linked", f"Your Discord account is now linked to **{gamertag}**. Anyone can now pick you in `/league player stats` and it'll pull your stats automatically."),
            ephemeral=True,
        )

    # ==================================================================
    # /league list
    # ==================================================================

    @list_group.command(name="list_clubs", description="List all clubs in the league")
    async def list_clubs(self, interaction: discord.Interaction):
        async with get_session() as session:
            teams = (await session.execute(select(Team).where(Team.is_active.is_(True)).order_by(Team.name))).scalars().all()
            if not teams:
                await interaction.response.send_message(embed=info_embed("No clubs", "No clubs have been added yet."))
                return
            lines = [f"• **{t.name}**" + (f" ({t.abbreviation})" if t.abbreviation else "") for t in teams]
        await interaction.response.send_message(embed=info_embed("League Clubs", "\n".join(lines)))

    @list_group.command(name="players", description="List all players registered to the league")
    @app_commands.describe(season="Season number (defaults to active)")
    async def list_players(self, interaction: discord.Interaction, season: int | None = None):
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return
            stmt = select(PlayerSeason, Player).join(Player, Player.id == PlayerSeason.player_id).where(PlayerSeason.season_id == s.id)
            rows = (await session.execute(stmt)).all()
            if not rows:
                await interaction.response.send_message(embed=info_embed("No players", f"No players registered for {s.name}."))
                return
            lines = [f"• {p.gamertag}" for _, p in rows]
            chunks = ["\n".join(lines[i : i + 40]) for i in range(0, len(lines), 40)]
        await interaction.response.send_message(embed=info_embed(f"League Players — {s.name}", chunks[0]))
        for chunk in chunks[1:]:
            await interaction.followup.send(embed=info_embed(f"League Players — {s.name}", chunk))

    @list_group.command(name="linked-players", description="List Discord accounts linked to a player gamertag")
    async def list_linked_players(self, interaction: discord.Interaction):
        async with get_session() as session:
            stmt = select(User, Player).join(Player, Player.id == User.player_id)
            rows = (await session.execute(stmt)).all()
            if not rows:
                await interaction.response.send_message(embed=info_embed("No links", "No Discord accounts have linked a gamertag yet."))
                return
            lines = [f"• <@{u.discord_id}> ↔ **{p.gamertag}**" for u, p in rows]
        await interaction.response.send_message(embed=info_embed("Linked Players", "\n".join(lines)))

    @list_group.command(name="recent-stat-leaders", description="Stat leaders over the last N games")
    @app_commands.describe(games="Number of most recent games to consider", season="Season number (defaults to active)")
    async def list_recent_leaders(self, interaction: discord.Interaction, games: int = 10, season: int | None = None):
        await interaction.response.defer()
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.followup.send(embed=error_embed("Season error", str(e)))
                return

            from bot.models import PlayerGameStat

            recent_game_ids = (
                await session.execute(select(Game.id).where(Game.season_id == s.id).order_by(Game.id.desc()).limit(games))
            ).scalars().all()
            if not recent_game_ids:
                await interaction.followup.send(embed=info_embed("No games", f"No games played yet in {s.name}."))
                return

            stmt = select(PlayerGameStat).where(PlayerGameStat.game_id.in_(recent_game_ids))
            lines_by_player: dict[int, dict] = {}
            for line in (await session.execute(stmt)).scalars().all():
                agg = lines_by_player.setdefault(line.player_id, {"goals": 0, "assists": 0, "points": 0})
                agg["goals"] += line.goals
                agg["assists"] += line.assists
                agg["points"] += line.points

            ranked = sorted(lines_by_player.items(), key=lambda kv: kv[1]["points"], reverse=True)[:10]
            lines = []
            for i, (player_id, agg) in enumerate(ranked, start=1):
                player = await session.get(Player, player_id)
                lines.append(f"`{i:>2}` **{player.gamertag}** — {agg['points']} pts ({agg['goals']}G {agg['assists']}A)")

        await interaction.followup.send(embed=info_embed(f"Stat Leaders — Last {games} Games ({s.name})", "\n".join(lines)))

    # ==================================================================
    # /league admin
    # ==================================================================

    @admin_group.command(name="add-logo", description="Set the league's own logo")
    @app_commands.describe(logo_url="Direct image URL for the league logo")
    @commissioner_only()
    async def admin_add_logo(self, interaction: discord.Interaction, logo_url: str):
        async with get_session() as session:
            setting = await session.scalar(
                select(GuildSetting).where(GuildSetting.guild_id == interaction.guild_id, GuildSetting.key == "league_logo_url")
            )
            if setting is None:
                session.add(GuildSetting(guild_id=interaction.guild_id, key="league_logo_url", value=logo_url))
            else:
                setting.value = logo_url
        await interaction.response.send_message(embed=success_embed("League logo set", "Saved."))

    @admin_group.command(name="add-background", description="Set a custom background photo used behind every graphic")
    @app_commands.describe(image_url="Direct image URL for the background photo")
    @commissioner_only()
    async def admin_add_background(self, interaction: discord.Interaction, image_url: str):
        async with get_session() as session:
            await set_league_background_url(session, interaction.guild_id, image_url)
        await interaction.response.send_message(
            embed=success_embed("Background set", "Every graphic will now use this photo as its background. Use `/league admin remove-background` to revert to the default look at any time.")
        )

    @admin_group.command(name="remove-background", description="Remove the custom background photo, reverting to the default look")
    @commissioner_only()
    async def admin_remove_background(self, interaction: discord.Interaction):
        async with get_session() as session:
            await set_league_background_url(session, interaction.guild_id, None)
        await interaction.response.send_message(embed=success_embed("Background removed", "Graphics have reverted to the default gradient look."))

    @admin_group.command(name="settings", description="View current league bot configuration")
    @commissioner_only()
    async def admin_settings(self, interaction: discord.Interaction):
        embed = info_embed(
            "League Bot Settings",
            f"Commissioner role: **{settings.role_commissioner}**\n"
            f"GM role: **{settings.role_gm}**\n"
            f"Game results channel: {'<#' + str(settings.channel_game_results) + '>' if settings.channel_game_results else '—'}\n"
            f"Standings channel: {'<#' + str(settings.channel_standings) + '>' if settings.channel_standings else '—'}\n"
            f"Stat leaders channel: {'<#' + str(settings.channel_stat_leaders) + '>' if settings.channel_stat_leaders else '—'}\n"
            f"Schedule channel: {'<#' + str(settings.channel_schedule) + '>' if settings.channel_schedule else '—'}\n"
            f"Awards channel: {'<#' + str(settings.channel_awards) + '>' if settings.channel_awards else '—'}\n\n"
            f"*Channel/role settings are configured via environment variables on the hosting platform.*",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @admin_group.command(name="submit-game", description="Import stats for a scheduled game from EA's Pro Clubs API")
    @app_commands.describe(
        schedule_game_number="The game number from /league schedule",
        season="Season number (defaults to active)",
        disable_auto_merge="Force-disable lagout auto-merge for this import (rare edge case override)",
    )
    @gm_only()
    async def admin_submit_game(
        self,
        interaction: discord.Interaction,
        schedule_game_number: int,
        season: int | None = None,
        disable_auto_merge: bool = False,
    ):
        await interaction.response.defer()
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.followup.send(embed=error_embed("Season error", str(e)))
                return
            try:
                result = await import_game(
                    session,
                    season_id=s.id,
                    game_number=schedule_game_number,
                    imported_by_discord_id=interaction.user.id,
                    disable_auto_merge=disable_auto_merge,
                )
            except ImportError_ as e:
                await interaction.followup.send(embed=error_embed("Couldn't import game", str(e)))
                return

            recap_text = await self._generate_and_attach_recap(session, result.game, result.home_team, result.away_team)
            league_logo_url = await get_league_logo_url(session, interaction.guild_id)
            background_url = await get_league_background_url(session, interaction.guild_id)
            graphic_path = await render_game_result(result.game, result.home_team, result.away_team, league_logo_url, background_url)
            result.game.result_graphic_path = graphic_path

            series = await record_series_result(session, result.schedule, result.game)
            series_status_text = None
            if series is not None:
                team_a = await session.get(Team, series.team_a_id)
                team_b = await session.get(Team, series.team_b_id)
                if series.winner_team_id is not None:
                    winner = team_a if series.winner_team_id == series.team_a_id else team_b
                    series_status_text = f"🏆 **{winner.name}** wins the {series.round_name} series {max(series.wins_a, series.wins_b)}-{min(series.wins_a, series.wins_b)}!"
                else:
                    series_status_text = f"{series.round_name}: **{team_a.name}** {series.wins_a} - {series.wins_b} **{team_b.name}**"

            unlinked = await find_unlinked_players_in_game(session, result.game.id)

            await refresh_all_channels(interaction.client, session)

        embed = success_embed("Game imported", f"**{result.home_team.name} {result.game.home_score} - {result.game.away_score} {result.away_team.name}**")
        if result.was_merged:
            embed.add_field(
                name="🔄 Lagout Auto-Merged",
                value="Two close-together matches between these clubs were automatically combined into one game's stats.",
                inline=False,
            )
        if recap_text:
            embed.add_field(name="Recap", value=recap_text, inline=False)
        if series_status_text:
            embed.add_field(name="Playoff Series", value=series_status_text, inline=False)
        if unlinked:
            lines = "\n".join(f"• **{u.gamertag}**, played this game with {u.team_name}." for u in unlinked)
            embed.add_field(name="⚠️ Unlinked Players Found", value=lines, inline=False)
        await interaction.followup.send(embed=embed, file=discord.File(graphic_path))
        await self._post_to_results_channel(interaction, embed, graphic_path)

    @admin_group.command(name="forfeit-game", description="Enforce a club forfeit on a match")
    @app_commands.describe(
        winning_team="Team that wins by forfeit",
        losing_team="Team that loses by forfeit",
        score="Recorded score, e.g. '1-0'",
        reason="Reason for the forfeit",
        game_number="Schedule game number this forfeit applies to (optional -- auto-detected if omitted)",
    )
    @app_commands.autocomplete(winning_team=team_name_autocomplete, losing_team=team_name_autocomplete)
    @commissioner_only()
    async def admin_forfeit_game(
        self,
        interaction: discord.Interaction,
        winning_team: str,
        losing_team: str,
        score: str,
        reason: str,
        game_number: int | None = None,
        season: int | None = None,
    ):
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return
            win_team = await session.scalar(select(Team).where(Team.name.ilike(winning_team)))
            lose_team = await session.scalar(select(Team).where(Team.name.ilike(losing_team)))
            if not win_team or not lose_team:
                await interaction.response.send_message(embed=error_embed("Unknown club", "Both clubs must exist."), ephemeral=True)
                return
            try:
                win_score, lose_score = (int(x) for x in score.replace(" ", "").split("-"))
            except ValueError:
                await interaction.response.send_message(embed=error_embed("Bad score format", "Use the format `1-0`."), ephemeral=True)
                return

            schedule = None
            if game_number is not None:
                schedule = await session.scalar(select(ScheduleGame).where(ScheduleGame.season_id == s.id, ScheduleGame.game_number == game_number))
            else:
                schedule = await find_pending_schedule_for_matchup(session, s.id, win_team.id, lose_team.id)

            is_playoff_game = bool(schedule and schedule.is_playoffs)

            now = dt.datetime.now(dt.timezone.utc)
            game = Game(
                season_id=s.id,
                schedule_id=schedule.id if schedule else None,
                home_team_id=win_team.id,
                away_team_id=lose_team.id,
                home_score=win_score,
                away_score=lose_score,
                is_forfeit=True,
                imported_at=now,
                played_at=now,
                imported_by_discord_id=interaction.user.id,
            )
            session.add(game)
            await session.flush()

            session.add(
                Forfeit(
                    season_id=s.id,
                    schedule_id=schedule.id if schedule else None,
                    game_id=game.id,
                    winning_team_id=win_team.id,
                    losing_team_id=lose_team.id,
                    winning_score=win_score,
                    losing_score=lose_score,
                    reason=reason,
                    entered_by_discord_id=interaction.user.id,
                    entered_at=now,
                )
            )

            if not is_playoff_game:
                await apply_team_season_delta(session, win_team.id, s.id, win_score, lose_score, False)
                await apply_team_season_delta(session, lose_team.id, s.id, lose_score, win_score, False)

            if schedule:
                schedule.status = ScheduleStatus.FORFEITED
                schedule.game_id = game.id

            await session.flush()
            if not is_playoff_game:
                await recompute_standings(session, s.id)

            league_logo_url = await get_league_logo_url(session, interaction.guild_id)
            background_url = await get_league_background_url(session, interaction.guild_id)
            graphic_path = await render_game_result(game, win_team, lose_team, league_logo_url, background_url)

            series_status_text = None
            if schedule and schedule.playoff_series_id:
                series = await record_series_result(session, schedule, game)
                if series is not None:
                    team_a = await session.get(Team, series.team_a_id)
                    team_b = await session.get(Team, series.team_b_id)
                    if series.winner_team_id is not None:
                        winner = team_a if series.winner_team_id == series.team_a_id else team_b
                        series_status_text = f"🏆 **{winner.name}** wins the {series.round_name} series {max(series.wins_a, series.wins_b)}-{min(series.wins_a, series.wins_b)}!"
                    else:
                        series_status_text = f"{series.round_name}: **{team_a.name}** {series.wins_a} - {series.wins_b} **{team_b.name}**"

            await refresh_all_channels(interaction.client, session)

        embed = success_embed("Forfeit recorded", f"**{win_team.name}** defeats **{lose_team.name}** {win_score}-{lose_score} by forfeit.\n*Reason: {reason}*")
        if series_status_text:
            embed.add_field(name="Playoff Series", value=series_status_text, inline=False)
        elif is_playoff_game:
            embed.add_field(name="Note", value="This was tagged as a playoff game, but no series was found to update.", inline=False)
        await interaction.response.send_message(embed=embed, file=discord.File(graphic_path))
        await self._post_to_results_channel(interaction, embed, graphic_path)

    @admin_group.command(name="delete-game", description="Delete an imported game and reverse all stats")
    @app_commands.describe(game_number="The schedule game number to undo")
    @commissioner_only()
    async def admin_delete_game(self, interaction: discord.Interaction, game_number: int, season: int | None = None):
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return
            schedule = await session.scalar(select(ScheduleGame).where(ScheduleGame.season_id == s.id, ScheduleGame.game_number == game_number))
            if not schedule or not schedule.game_id:
                await interaction.response.send_message(embed=error_embed("Nothing to delete", f"Game #{game_number} has no imported result."), ephemeral=True)
                return
            game = await session.get(Game, schedule.game_id)
            await reverse_game(session, game)
            await refresh_all_channels(interaction.client, session)
        await interaction.response.send_message(embed=success_embed("Game deleted", f"Game #{game_number} was removed and all stats/standings reversed."))

    @admin_group.command(name="generate-playoffs", description="Seed a single-elimination playoff bracket from the current standings")
    @app_commands.describe(
        num_teams="How many teams make the bracket -- must be a power of 2 (4, 8, 16...)",
        best_of="Games per series -- must be odd (3, 5, 7...)",
    )
    @commissioner_only()
    async def admin_generate_playoffs(self, interaction: discord.Interaction, num_teams: int, best_of: int = 5, season: int | None = None):
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            existing = await get_bracket(session, s.id)
            if existing:
                await interaction.response.send_message(
                    embed=error_embed("Bracket already exists", f"{s.name} already has a playoff bracket."), ephemeral=True
                )
                return

            entries = (
                await session.execute(select(StandingsEntry).where(StandingsEntry.season_id == s.id).order_by(StandingsEntry.rank))
            ).scalars().all()
            if len(entries) < num_teams:
                await interaction.response.send_message(
                    embed=error_embed("Not enough teams", f"{s.name}'s standings only has {len(entries)} teams, but you asked for {num_teams}."),
                    ephemeral=True,
                )
                return

            seeded_team_ids = [e.team_id for e in entries[:num_teams]]

            try:
                created = await generate_bracket(session, s.id, seeded_team_ids, best_of)
            except PlayoffError as e:
                await interaction.response.send_message(embed=error_embed("Couldn't generate bracket", str(e)), ephemeral=True)
                return

            lines = []
            for series in created:
                team_a = await session.get(Team, series.team_a_id)
                team_b = await session.get(Team, series.team_b_id)
                lines.append(f"({series.seed_a}) {team_a.name} vs ({series.seed_b}) {team_b.name}")

        await interaction.response.send_message(
            embed=success_embed(f"{created[0].round_name} bracket generated", "\n".join(lines) + f"\n\nBest of {best_of}. Enter games with `/league admin submit-game` as usual.")
        )

    @admin_group.command(name="advance-round", description="Advance to the next playoff round once all series in the current round are decided")
    @app_commands.describe(round_order="Which round number to advance from (1 = first round, 2 = second, etc.)")
    @commissioner_only()
    async def admin_advance_round(self, interaction: discord.Interaction, round_order: int, season: int | None = None):
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            try:
                created = await advance_round(session, s.id, round_order)
            except PlayoffError as e:
                await interaction.response.send_message(embed=error_embed("Can't advance yet", str(e)), ephemeral=True)
                return

            lines = []
            for series in created:
                team_a = await session.get(Team, series.team_a_id)
                team_b = await session.get(Team, series.team_b_id)
                lines.append(f"{team_a.name} vs {team_b.name}")

        await interaction.response.send_message(embed=success_embed(f"{created[0].round_name} generated", "\n".join(lines)))

    @admin_group.command(name="generate-schedule", description="Auto-generate a full round-robin schedule for the league")
    @app_commands.describe(
        times_through="How many times each team plays every other team (2 = home-and-away, like a normal season)",
        teams="Comma-separated team names to include (optional -- defaults to every active club in the league)",
        starting_game_number="First game number to use (optional -- defaults to continuing after any existing schedule)",
    )
    @commissioner_only()
    async def admin_generate_schedule(
        self,
        interaction: discord.Interaction,
        times_through: int = 2,
        teams: str | None = None,
        starting_game_number: int | None = None,
        season: int | None = None,
    ):
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            if teams:
                names = [t.strip() for t in teams.split(",") if t.strip()]
                team_objs = []
                for name in names:
                    team = await session.scalar(select(Team).where(Team.name.ilike(name)))
                    if not team:
                        await interaction.response.send_message(embed=error_embed("Unknown club", f"No club named **{name}**."), ephemeral=True)
                        return
                    team_objs.append(team)
            else:
                team_objs = (
                    await session.execute(select(Team).where(Team.is_active.is_(True)).order_by(Team.name))
                ).scalars().all()

            if len(team_objs) < 2:
                await interaction.response.send_message(
                    embed=error_embed("Not enough clubs", "Need at least 2 clubs to generate a schedule -- add clubs with `/league club add` first."),
                    ephemeral=True,
                )
                return

            try:
                matchups = generate_round_robin([t.id for t in team_objs], times_through=times_through)
            except ValueError as e:
                await interaction.response.send_message(embed=error_embed("Couldn't generate schedule", str(e)), ephemeral=True)
                return

            if starting_game_number is not None:
                next_number = starting_game_number
            else:
                existing_numbers = (
                    await session.execute(select(ScheduleGame.game_number).where(ScheduleGame.season_id == s.id))
                ).scalars().all()
                next_number = (max(existing_numbers) + 1) if existing_numbers else 1

            # Check the whole range we're about to use for collisions BEFORE
            # inserting anything -- this is what turns a raw database crash
            # (which happened if old schedule rows were still present, e.g.
            # after removing some teams but not clearing their games) into a
            # clear, actionable error message instead.
            proposed_numbers = set(range(next_number, next_number + len(matchups)))
            colliding = (
                await session.execute(
                    select(ScheduleGame.game_number).where(
                        ScheduleGame.season_id == s.id, ScheduleGame.game_number.in_(proposed_numbers)
                    )
                )
            ).scalars().all()
            if colliding:
                await interaction.response.send_message(
                    embed=error_embed(
                        "Game numbers already taken",
                        f"{s.name} already has games numbered {min(colliding)}-{max(colliding)} (or overlapping). "
                        f"Use `/league admin clear-schedule` to remove the old schedule first, or pick a different "
                        f"`starting_game_number` that doesn't overlap with existing games.",
                    ),
                    ephemeral=True,
                )
                return

            created_count = 0
            for m in matchups:
                session.add(
                    ScheduleGame(
                        season_id=s.id,
                        game_number=next_number,
                        week=m.round_number,
                        home_team_id=m.home_team_id,
                        away_team_id=m.away_team_id,
                    )
                )
                next_number += 1
                created_count += 1

        await interaction.response.send_message(
            embed=success_embed(
                "Schedule generated",
                f"Created **{created_count}** games across **{matchups[-1].round_number}** weeks for **{len(team_objs)}** clubs "
                f"(each team plays every other team **{times_through}x**).\n\nGame numbers **{next_number - created_count}**–**{next_number - 1}**. "
                f"Use `/league schedule view` to see the full schedule.",
            )
        )

    @admin_group.command(name="clear-schedule", description="Delete a season's schedule so it can be regenerated cleanly")
    @app_commands.describe(
        include_played="Also delete games that already have results imported (DESTRUCTIVE -- defaults to False, only clears unplayed games)"
    )
    @commissioner_only()
    async def admin_clear_schedule(self, interaction: discord.Interaction, include_played: bool = False, season: int | None = None):
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            stmt = select(ScheduleGame).where(ScheduleGame.season_id == s.id)
            if not include_played:
                stmt = stmt.where(ScheduleGame.status == ScheduleStatus.SCHEDULED)
            games = (await session.execute(stmt)).scalars().all()

            if not games:
                await interaction.response.send_message(
                    embed=info_embed("Nothing to clear", f"No {'games' if include_played else 'unplayed games'} found for {s.name}.")
                )
                return

            played_count = sum(1 for g in games if g.status != ScheduleStatus.SCHEDULED)
            deleted_count = len(games)
            for g in games:
                await session.delete(g)

        await interaction.response.send_message(
            embed=success_embed(
                "Schedule cleared",
                f"Deleted **{deleted_count}** {'games' if include_played else 'unplayed games'} from {s.name}'s schedule."
                + (f" This included **{played_count}** already-played games." if include_played and played_count else ""),
            )
        )

    # ==================================================================
    # /league refresh
    # ==================================================================

    @refresh_group.command(name="standings", description="Manually re-post the standings graphic")
    @commissioner_only()
    async def refresh_standings(self, interaction: discord.Interaction, season: int | None = None):
        await interaction.response.defer()
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.followup.send(embed=error_embed("Season error", str(e)))
                return
            entries = (await session.execute(select(StandingsEntry).where(StandingsEntry.season_id == s.id).order_by(StandingsEntry.rank))).scalars().all()
            if not entries:
                await interaction.followup.send(embed=info_embed("No standings", f"No games played yet in {s.name}."))
                return
            rows = [(e, await session.get(Team, e.team_id)) for e in entries]
            league_logo_url = await get_league_logo_url(session, interaction.guild_id)
            background_url = await get_league_background_url(session, interaction.guild_id)
            path = await render_standings(s.name, rows, league_logo_url, background_url)
            await refresh_all_channels(interaction.client, session)
        await interaction.followup.send(file=discord.File(path))

    @refresh_group.command(name="stat-leaders", description="Manually re-post the combined stat leaders graphic")
    @commissioner_only()
    async def refresh_stat_leaders(self, interaction: discord.Interaction, season: int | None = None):
        await interaction.response.defer()
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.followup.send(embed=error_embed("Season error", str(e)))
                return

            categories = [
                ("Points", await points_leaders(session, s.id, limit=5)),
                ("Goals", await goals_leaders(session, s.id, limit=5)),
                ("Assists", await assists_leaders(session, s.id, limit=5)),
                ("Hits", await hits_leaders(session, s.id, limit=5)),
                ("PIM", await pim_leaders(session, s.id, limit=5)),
                ("Faceoff %", await faceoff_pct_leaders(session, s.id, limit=5)),
                ("Takeaways", await takeaways_leaders(session, s.id, limit=5)),
                ("Interceptions", await interceptions_leaders(session, s.id, limit=5)),
                ("Blocked Shots", await blocked_shots_leaders(session, s.id, limit=5)),
                ("GAA", await gaa_leaders(session, s.id, limit=5)),
                ("Save %", await goalie_leaders(session, s.id, limit=5)),
                ("Shutouts", await shutouts_leaders(session, s.id, limit=5)),
            ]

            league_logo_url = await get_league_logo_url(session, interaction.guild_id)
            background_url = await get_league_background_url(session, interaction.guild_id)
            path = await render_combined_leaders_board(s.name, categories, league_logo_url, background_url)
            await refresh_all_channels(interaction.client, session)
        await interaction.followup.send(file=discord.File(path))

    @refresh_group.command(name="match-result", description="Re-post the result graphic/recap for an already-imported game")
    @app_commands.describe(game_number="Schedule game number")
    @commissioner_only()
    async def refresh_match_result(self, interaction: discord.Interaction, game_number: int, season: int | None = None):
        await interaction.response.defer()
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.followup.send(embed=error_embed("Season error", str(e)))
                return
            schedule = await session.scalar(select(ScheduleGame).where(ScheduleGame.season_id == s.id, ScheduleGame.game_number == game_number))
            if not schedule or not schedule.game_id:
                await interaction.followup.send(embed=error_embed("No result", f"Game #{game_number} hasn't been imported yet."))
                return
            game = await session.get(Game, schedule.game_id)
            home_team = await session.get(Team, game.home_team_id)
            away_team = await session.get(Team, game.away_team_id)
            league_logo_url = await get_league_logo_url(session, interaction.guild_id)
            background_url = await get_league_background_url(session, interaction.guild_id)
            path = await render_game_result(game, home_team, away_team, league_logo_url, background_url)
            embed = info_embed(f"{home_team.name} {game.home_score} - {game.away_score} {away_team.name}", game.recap_text or "")
        await interaction.followup.send(embed=embed, file=discord.File(path))

    @refresh_group.command(name="fixture", description="Re-post the current schedule")
    @commissioner_only()
    async def refresh_fixture(self, interaction: discord.Interaction, season: int | None = None):
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return
            games = (await session.execute(select(ScheduleGame).where(ScheduleGame.season_id == s.id).order_by(ScheduleGame.game_number))).scalars().all()
            if not games:
                await interaction.response.send_message(embed=info_embed("No schedule", f"No games scheduled yet for {s.name}."))
                return
            lines = []
            for g in games[:40]:
                home = await session.get(Team, g.home_team_id)
                away = await session.get(Team, g.away_team_id)
                icon = "✅" if g.status == ScheduleStatus.PLAYED else ("🚫" if g.status == ScheduleStatus.FORFEITED else "🕒")
                lines.append(f"{icon} `#{g.game_number}` {home.name} vs {away.name}")
        await interaction.response.send_message(embed=info_embed(f"Schedule — {s.name}", "\n".join(lines)))

    @refresh_group.command(name="playoffs", description="Re-post the playoff bracket")
    @commissioner_only()
    async def refresh_playoffs(self, interaction: discord.Interaction, season: int | None = None):
        await interaction.response.defer()
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.followup.send(embed=error_embed("Season error", str(e)))
                return

            rounds = await get_bracket(session, s.id)
            if not rounds:
                await interaction.followup.send(
                    embed=info_embed("No bracket yet", f"No playoff bracket has been generated for {s.name}. Use `/league admin generate-playoffs` first.")
                )
                return

            all_team_ids = {t_id for round_series in rounds for series in round_series for t_id in (series.team_a_id, series.team_b_id)}
            teams_by_id = {t_id: await session.get(Team, t_id) for t_id in all_team_ids}
            league_logo_url = await get_league_logo_url(session, interaction.guild_id)
            background_url = await get_league_background_url(session, interaction.guild_id)
            path = await render_playoff_bracket(s.name, rounds, teams_by_id, league_logo_url, background_url)

        await interaction.followup.send(file=discord.File(path))

    # ==================================================================
    # /league schedule
    # ==================================================================

    @schedule_group.command(name="add", description="Schedule a match")
    @app_commands.describe(game_number="Unique game number, used by /league admin submit-game", home_team="Home club", away_team="Away club", week="Week number")
    @app_commands.autocomplete(home_team=team_name_autocomplete, away_team=team_name_autocomplete)
    @commissioner_only()
    async def schedule_add(self, interaction: discord.Interaction, game_number: int, home_team: str, away_team: str, week: int | None = None, season: int | None = None):
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return
            home = await session.scalar(select(Team).where(Team.name.ilike(home_team)))
            away = await session.scalar(select(Team).where(Team.name.ilike(away_team)))
            if not home or not away:
                await interaction.response.send_message(embed=error_embed("Unknown club", "Both clubs must already exist (`/league club add`)."), ephemeral=True)
                return
            existing = await session.scalar(select(ScheduleGame).where(ScheduleGame.season_id == s.id, ScheduleGame.game_number == game_number))
            if existing:
                await interaction.response.send_message(embed=error_embed("Already scheduled", f"Game #{game_number} already exists for {s.name}."), ephemeral=True)
                return
            session.add(ScheduleGame(season_id=s.id, game_number=game_number, week=week, home_team_id=home.id, away_team_id=away.id))
        await interaction.response.send_message(embed=success_embed("Scheduled", f"Game #{game_number}: **{home_team}** vs **{away_team}** added to {s.name}."))

    @schedule_group.command(name="view", description="View the full schedule")
    async def schedule_view(self, interaction: discord.Interaction, season: int | None = None):
        await self._send_schedule(interaction, season=season, week=None, status=None)

    @schedule_group.command(name="week", description="View the schedule for a specific week")
    @app_commands.describe(week="Week number")
    async def schedule_week(self, interaction: discord.Interaction, week: int, season: int | None = None):
        await self._send_schedule(interaction, season=season, week=week, status=None)

    @schedule_group.command(name="pending", description="View games not yet played")
    async def schedule_pending(self, interaction: discord.Interaction, season: int | None = None):
        await self._send_schedule(interaction, season=season, week=None, status=ScheduleStatus.SCHEDULED)

    # ==================================================================
    # top-level /league postpone-game
    # ==================================================================

    @league_group.command(name="postpone-game", description="Postpone a scheduled game to be played later")
    @app_commands.describe(game_number="Schedule game number", reason="Reason for postponing")
    @commissioner_only()
    async def postpone_game(self, interaction: discord.Interaction, game_number: int, reason: str, season: int | None = None):
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return
            schedule = await session.scalar(select(ScheduleGame).where(ScheduleGame.season_id == s.id, ScheduleGame.game_number == game_number))
            if not schedule:
                await interaction.response.send_message(embed=error_embed("Not found", f"No schedule entry for game #{game_number}."), ephemeral=True)
                return
            schedule.status = ScheduleStatus.POSTPONED
        await interaction.response.send_message(embed=success_embed("Game postponed", f"Game #{game_number} marked postponed.\n*Reason: {reason}*"))

    # ==================================================================
    # helpers
    # ==================================================================

    @staticmethod
    async def _resolve_player(
        session, interaction: discord.Interaction, gamertag: str | None, discord_user: "discord.Member | discord.User | None" = None
    ) -> Player | None:
        if gamertag:
            return await session.scalar(select(Player).where(Player.gamertag.ilike(gamertag)))
        target_id = discord_user.id if discord_user else interaction.user.id
        user = await session.scalar(select(User).where(User.discord_id == target_id))
        if user and user.player_id:
            return await session.get(Player, user.player_id)
        return None

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
                icon = {
                    ScheduleStatus.SCHEDULED: "🕒",
                    ScheduleStatus.PLAYED: "✅",
                    ScheduleStatus.FORFEITED: "🚫",
                    ScheduleStatus.POSTPONED: "⏸️",
                    ScheduleStatus.CANCELLED: "❌",
                }[g.status]
                week_str = f"Wk{g.week} " if g.week else ""
                lines.append(f"{icon} `#{g.game_number}` {week_str}{home.name} vs {away.name}")
            chunks = ["\n".join(lines[i : i + 25]) for i in range(0, len(lines), 25)]
        title = f"Schedule — {s.name}"
        await interaction.response.send_message(embed=info_embed(title, chunks[0]))
        for chunk in chunks[1:]:
            await interaction.followup.send(embed=info_embed(title, chunk))

    async def _generate_and_attach_recap(self, session, game: Game, home_team: Team, away_team: Team) -> str:
        from bot.models import GoalieGameStat, PlayerGameStat

        home_ts = await session.scalar(select(TeamSeason).where(TeamSeason.team_id == home_team.id, TeamSeason.season_id == game.season_id))
        away_ts = await session.scalar(select(TeamSeason).where(TeamSeason.team_id == away_team.id, TeamSeason.season_id == game.season_id))
        home_standing = await session.scalar(select(StandingsEntry).where(StandingsEntry.team_id == home_team.id, StandingsEntry.season_id == game.season_id))
        away_standing = await session.scalar(select(StandingsEntry).where(StandingsEntry.team_id == away_team.id, StandingsEntry.season_id == game.season_id))

        player_rows = (await session.execute(select(PlayerGameStat).where(PlayerGameStat.game_id == game.id))).scalars().all()
        goalie_rows = (await session.execute(select(GoalieGameStat).where(GoalieGameStat.game_id == game.id))).scalars().all()
        player_pairs = [(await session.get(Player, pr.player_id), pr) for pr in player_rows]
        goalie_pairs = [(await session.get(Player, gr.player_id), gr) for gr in goalie_rows]
        top_performers = format_top_performers(player_pairs, goalie_pairs)

        ctx = RecapContext(
            game=game,
            home_team=home_team,
            away_team=away_team,
            home_team_season=home_ts,
            away_team_season=away_ts,
            standings_rank_home=home_standing.rank if home_standing else 0,
            standings_rank_away=away_standing.rank if away_standing else 0,
            top_performers=top_performers,
        )
        recap = await generate_recap(ctx)
        game.recap_text = recap
        return recap

    async def _post_to_results_channel(self, interaction: discord.Interaction, embed: discord.Embed, graphic_path: str) -> None:
        if not settings.channel_game_results:
            return
        channel = interaction.client.get_channel(settings.channel_game_results)
        if channel is None:
            return
        try:
            await channel.send(embed=embed, file=discord.File(graphic_path))
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(LeagueCog(bot))
