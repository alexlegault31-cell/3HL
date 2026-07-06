"""
The centerpiece of the bot: `/entergame`, plus `/game delete`, `/game edit`,
and the manual `/game ffw` forfeit flow.

This cog is intentionally thin — all the real logic lives in
`services/stat_importer.py`, `services/recap_generator.py`, and
`bot/graphics/*`. The cog's job is: validate Discord-level permissions,
call the service layer, and post the result (graphic + recap) into
#game-results.
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
from bot.graphics.game_result_graphic import render_game_result
from bot.models import Forfeit, Game, GoalieGameStat, Player, PlayerGameStat, ScheduleGame, Team, TeamSeason
from bot.models.schedule import ScheduleStatus
from bot.services.recap_generator import RecapContext, format_top_performers, generate_recap
from bot.services.season_service import SeasonNotFound, resolve_season
from bot.services.standings_service import recompute_standings
from bot.services.stat_importer import ImportError_, apply_team_season_delta, import_game, reverse_game, undo_team_result
from bot.utils.checks import commissioner_only, gm_only
from bot.utils.embeds import error_embed, info_embed, success_embed


class GameCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    game_group = app_commands.Group(name="game", description="Game management")

    # ------------------------------------------------------------------
    # /entergame — top level command, not nested under /game, per spec
    # ------------------------------------------------------------------

    @app_commands.command(name="entergame", description="Import stats for a scheduled game from ChelStats")
    @app_commands.describe(schedule_game_number="The game number from /schedule", season="Season number (defaults to active)")
    @gm_only()
    async def entergame(self, interaction: discord.Interaction, schedule_game_number: int, season: int | None = None):
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
                )
            except ImportError_ as e:
                await interaction.followup.send(embed=error_embed("Couldn't import game", str(e)))
                return

            recap_text = await self._generate_and_attach_recap(session, result.game, result.home_team, result.away_team)
            graphic_path = render_game_result(result.game, result.home_team, result.away_team)
            result.game.result_graphic_path = graphic_path
            await refresh_all_channels(interaction.client, session)

        embed = success_embed(
            "Game imported",
            f"**{result.home_team.name} {result.game.home_score} - {result.game.away_score} {result.away_team.name}**",
        )
        if recap_text:
            embed.add_field(name="Recap", value=recap_text, inline=False)

        file = discord.File(graphic_path)
        await interaction.followup.send(embed=embed, file=file)
        await self._post_to_results_channel(interaction, embed, graphic_path)

    @game_group.command(name="delete", description="Delete an imported game and reverse all stats")
    @app_commands.describe(game_number="The schedule game number to undo")
    @commissioner_only()
    async def delete(self, interaction: discord.Interaction, game_number: int, season: int | None = None):
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            schedule = await session.scalar(
                select(ScheduleGame).where(ScheduleGame.season_id == s.id, ScheduleGame.game_number == game_number)
            )
            if not schedule or not schedule.game_id:
                await interaction.response.send_message(embed=error_embed("Nothing to delete", f"Game #{game_number} has no imported result."), ephemeral=True)
                return

            game = await session.get(Game, schedule.game_id)
            await reverse_game(session, game)
            await refresh_all_channels(interaction.client, session)

        await interaction.response.send_message(
            embed=success_embed("Game deleted", f"Game #{game_number} was removed and all stats/standings reversed.")
        )

    @game_group.command(name="edit", description="Manually correct the score of an imported game")
    @app_commands.describe(game_number="Schedule game number", home_score="Corrected home score", away_score="Corrected away score")
    @commissioner_only()
    async def edit(self, interaction: discord.Interaction, game_number: int, home_score: int, away_score: int, season: int | None = None):
        async with get_session() as session:
            try:
                s = await resolve_season(session, season)
            except SeasonNotFound as e:
                await interaction.response.send_message(embed=error_embed("Season error", str(e)), ephemeral=True)
                return

            schedule = await session.scalar(
                select(ScheduleGame).where(ScheduleGame.season_id == s.id, ScheduleGame.game_number == game_number)
            )
            if not schedule or not schedule.game_id:
                await interaction.response.send_message(embed=error_embed("No game", f"Game #{game_number} hasn't been imported yet."), ephemeral=True)
                return

            game = await session.get(Game, schedule.game_id)
            home_ts = await session.scalar(select(TeamSeason).where(TeamSeason.team_id == game.home_team_id, TeamSeason.season_id == s.id))
            away_ts = await session.scalar(select(TeamSeason).where(TeamSeason.team_id == game.away_team_id, TeamSeason.season_id == s.id))

            # Undo old result's effect on team records, apply corrected one.
            undo_team_result(home_ts, game.home_score, game.away_score, game.went_to_overtime)
            undo_team_result(away_ts, game.away_score, game.home_score, game.went_to_overtime)

            game.home_score = home_score
            game.away_score = away_score

            await apply_team_season_delta(session, game.home_team_id, s.id, home_score, away_score, game.went_to_overtime)
            await apply_team_season_delta(session, game.away_team_id, s.id, away_score, home_score, game.went_to_overtime)

            await session.flush()
            await recompute_standings(session, s.id)
            await refresh_all_channels(interaction.client, session)

        await interaction.response.send_message(
            embed=success_embed("Game corrected", f"Game #{game_number} updated to {home_score}-{away_score}. Note: per-player stat lines were NOT changed, only the team score/record.")
        )

    @game_group.command(name="ffw", description="Record a manual forfeit")
    @app_commands.describe(
        winning_team="Team that wins by forfeit",
        losing_team="Team that loses by forfeit",
        score="Recorded score, e.g. '1-0'",
        reason="Reason for the forfeit",
        game_number="Schedule game number this forfeit applies to (optional)",
    )
    @commissioner_only()
    async def ffw(
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
                await interaction.response.send_message(embed=error_embed("Unknown team", "Both teams must exist."), ephemeral=True)
                return

            try:
                win_score, lose_score = (int(x) for x in score.replace(" ", "").split("-"))
            except ValueError:
                await interaction.response.send_message(embed=error_embed("Bad score format", "Use the format `1-0`."), ephemeral=True)
                return

            schedule = None
            if game_number is not None:
                schedule = await session.scalar(
                    select(ScheduleGame).where(ScheduleGame.season_id == s.id, ScheduleGame.game_number == game_number)
                )

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

            await apply_team_season_delta(session, win_team.id, s.id, win_score, lose_score, False)
            await apply_team_season_delta(session, lose_team.id, s.id, lose_score, win_score, False)

            if schedule:
                schedule.status = ScheduleStatus.FORFEITED
                schedule.game_id = game.id

            await session.flush()
            await recompute_standings(session, s.id)
            await refresh_all_channels(interaction.client, session)
            graphic_path = render_game_result(game, win_team, lose_team)

        embed = success_embed(
            "Forfeit recorded",
            f"**{win_team.name}** defeats **{lose_team.name}** {win_score}-{lose_score} by forfeit.\n*Reason: {reason}*",
        )
        await interaction.response.send_message(embed=embed, file=discord.File(graphic_path))
        await self._post_to_results_channel(interaction, embed, graphic_path)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    async def _generate_and_attach_recap(self, session, game: Game, home_team: Team, away_team: Team) -> str:
        from bot.models import StandingsEntry

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
    await bot.add_cog(GameCog(bot))
