"""
One-time historical import: 3HL Season 2026, sourced from MyStatsOnline
(mystatsonline.com/hockey, IDLeague=76491). Creates a closed-out PAST
season (not active) with final standings, skater/goalie season totals,
and the full playoff bracket (Montreal Canadiens won the championship).

This is meant to be run ONCE via /league admin import-legacy-2026, then
the command can be deleted from the codebase -- it's not a reusable
general-purpose importer, just a one-time historical backfill.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.database import get_session
from bot.models import Player, PlayerSeason, PlayoffSeries, Season, Team, TeamSeason
from bot.utils.checks import commissioner_only
from bot.utils.embeds import error_embed, success_embed

# (name, GP, W, L, OTL, PTS, GF, GA) -- taken directly from MyStatsOnline's
# final Season 2026 standings table, not re-derived or reconciled.
TEAM_STANDINGS = [
    ("Montreal Canadiens", 16, 13, 3, 0, 26, 140, 71),
    ("Edmonton Oilers", 16, 8, 8, 0, 16, 89, 92),
    ("Buffalo Sabres", 11, 7, 4, 0, 14, 70, 57),
    ("Vancouver Canucks", 10, 4, 4, 0, 10, 34, 36),
    ("San Jose Sharks", 4, 0, 2, 0, 2, 3, 15),
    ("Arizona Tropics", 5, 1, 4, 0, 2, 24, 39),
    ("Savannah Ghost Pirates", 4, 0, 4, 0, 0, 9, 31),
    ("Winnipeg Jets", 4, 0, 4, 0, 0, 15, 43),
]

TEAM_ABBR_TO_NAME = {
    "MTL": "Montreal Canadiens", "EDM": "Edmonton Oilers", "BUF": "Buffalo Sabres",
    "VAN": "Vancouver Canucks", "SJS": "San Jose Sharks", "ARI": "Arizona Tropics",
    "SGP": "Savannah Ghost Pirates", "WIN": "Winnipeg Jets",
}

# (gamertag, team_abbr_or_None, position, gp, g, a, plus_minus, hits)
SKATERS = [
    ("BOOST GREECY", "MTL", "F", 7, 17, 30, 20, 40),
    ("\u2ba7\u06ee\u1d17\u06ee\u06ee\u1d17\u1d0f", "VAN", "F", 4, 8, 8, 4, 20),
    ("Stutzle", "MTL", "F", 4, 18, 21, 28, 46),
    ("-\u00c3SkaR0V-", "VAN", "F", 1, 5, 1, 4, 4),
    ("Fairclothttv", "SGP", "F", 1, 4, 1, -5, 4),
    ("s h b i u r", "MTL", "F", 5, 11, 26, 22, 22),
    ("HQKikass23415", "ARI", "F", 2, 1, 1, -12, 1),
    ("Hockey_dax91", "ARI", "F", 1, 0, 0, 0, 0),
    ("Matthieu", "ARI", "F", 2, 1, 1, -12, 9),
    ("Demidxv x 93", "WIN", "F", 2, 7, 1, -13, 24),
    ("iR0sty", "MTL", "F", 6, 19, 20, 24, 35),
    ("ruthlessdefender", "BUF", "F", 1, 2, 2, 6, 0),
    ("x99xQCxDemon", "VAN", "F", 3, 11, 10, 14, 1),
    ("SpaceCadetM", "BUF", "F", 2, 6, 5, -3, 10),
    ("NoLuckJustClutch", "VAN", "F", 2, 0, 8, 12, 16),
    ("x_Hxll_9x", "BUF", "F", 6, 9, 23, 14, 6),
    ("yuhmm.", "MTL", "F", 1, 3, 1, -3, 10),
    ("BureauCHELQC", "EDM", "F", 1, 2, 2, 6, 0),
    ("FireStar QC", "BUF", "F", 1, 2, 2, 6, 0),
    ("Joeypaisan", "EDM", "F", 1, 2, 2, 6, 0),
    ("ShIfTy", "EDM", "F", 3, 1, 6, -8, 8),
    ("lil420baguette", "EDM", "F", 8, 20, 17, 10, 51),
    ("mr_gilligan", "EDM", "F", 1, 2, 2, 6, 0),
    ("tugg2694", "EDM", "F", 6, 3, 22, -12, 12),
    ("xSundin", "EDM", "F", 5, 16, 5, 7, 16),
    ("Beaudreeez", "EDM", "F", 6, 11, 18, -12, 39),
    ("F4MoUs Red BUL", "WIN", "F", 2, 5, 3, -13, 1),
    ("Badmemory_95", "BUF", "F", 1, 2, 2, 6, 0),
    ("Jam-16-mac", "MTL", "F", 2, 6, 6, 6, 1),
    ("Fancargo", "SGP", "F", 4, 0, 4, -22, 14),
    ("Beaudreeez2", "EDM", "C", 1, 5, 2, 7, 8),
    ("BioMorphX", "EDM", "D", 1, 1, 3, 7, 1),
    ("Fleury x 29", "BUF", "F", 3, 6, 12, 1, 24),
    ("XxROYxXQC", None, "F", 2, 2, 10, 13, 3),
    ("Alexi_Hockey", "WIN", "F", 1, 1, 3, -8, 3),
    ("Clutch98Qc", "VAN", "F", 4, 2, 7, 4, 8),
    ("noxyKO", "MTL", "F", 2, 17, 3, 15, 18),
    ("xl Brody lx", "MTL", "F", 3, 5, 19, 23, 22),
    ("TiZz__Creepy", "VAN", "F", 6, 9, 20, 10, 39),
    ("Maxx87", "EDM", "F", 7, 7, 15, 5, 8),
    ("nuckssss", "EDM", "F", 1, 2, 2, 6, 0),
    ("Qc SpitFire89", "BUF", "F", 6, 20, 16, 14, 26),
    ("F4MoUs GuRu", "WIN", "F", 1, 0, 3, -8, 1),
    ("xOshie-77", "ARI", "F", 2, 0, 2, -12, 4),
    ("Jonmck970", "WIN", "F", 2, 2, 5, -13, 11),
    ("xxRoiiDzxx", "SGP", "F", 4, 3, 4, -22, 17),
    ("Klown 93", None, "F", 3, 10, 13, 17, 9),
    ("l Wreck Boi", "SGP", "F", 3, 2, 1, -17, 14),
    ("Henteye ll", "BUF", "F", 3, 3, 11, 0, 0),
    ("Kessl19", "EDM", "F", 4, 6, 9, 15, 20),
    ("jsxtay14", "WIN", "F", 1, 1, 2, -8, 0),
    ("Chade9834", "BUF", "F", 3, 2, 10, -9, 11),
    ("malekxx94", "MTL", "F", 3, 15, 7, 13, 9),
    ("kaizen x 96", "MTL", "F", 4, 15, 15, 21, 18),
    ("Dairy Cannonss", "EDM", "F", 3, 11, 5, -1, 9),
]

# (gamertag, team_abbr_or_None, gp, sa, ga, sv, gaa_or_None, svp, so, w, l)
GOALIES = [
    ("s h b i u r (G)", "MTL", 3, 66, 14, 52, None, 0.788, 0, 3, 0),
    ("HQKikass23415 (G)", "ARI", 1, 0, 0, 0, None, 0.000, 0, 0, 0),
    ("Demidxv x 93 (G)", "WIN", 1, 30, 13, 17, None, 0.567, 0, 0, 1),
    ("FAMILY FIRST #320", "MTL", 3, 22, 10, 12, None, 0.545, 1, 3, 0),
    ("N0TCUTPOW3R", "MTL", 3, 47, 16, 31, None, 0.660, 1, 2, 1),
    ("ShIfTy (G)", "EDM", 9, 150, 67, 83, None, 0.553, 1, 4, 4),
    ("Beaudreeez (G)", "EDM", 1, 16, 1, 15, None, 0.938, 0, 1, 0),
    ("BioMorphX (G)", "EDM", 3, 36, 12, 24, 12.00, 0.667, 1, 2, 1),
    ("Fleury x 29 (G)", "BUF", 1, 2, 2, 0, 2.00, 0.000, 0, 1, 0),
    ("qcvroum98", "MTL", 1, 35, 5, 30, None, 0.857, 0, 1, 0),
    ("Morrello2599", "ARI", 2, 26, 8, 18, 8.00, 0.692, 1, 0, 2),
    ("HomicideQC", "SGP", 3, 50, 26, 24, 8.67, 0.480, 0, 0, 3),
    ("PittSteelers123", "SGP", 1, 8, 5, 3, 5.00, 0.375, 0, 0, 1),
    ("Clutch98Qc (G)", "VAN", 1, 8, 0, 8, None, 1.000, 1, 1, 0),
    ("The_Chad_is_gr8", "VAN", 7, 64, 34, 30, None, 0.469, 1, 5, 1),
    ("F4MoUs GuRu (G)", "WIN", 1, 21, 11, 10, None, 0.476, 0, 0, 1),
    ("lBIGJO l", None, 3, 51, 9, 42, 3.00, 0.824, 0, 3, 0),
    ("Xx_Fowler_32xx", "BUF", 4, 75, 33, 42, None, 0.560, 0, 2, 2),
    ("Lucifer7961", "MTL", 2, 37, 11, 26, None, 0.703, 0, 2, 0),
    ("Dairy Cannonss (G)", "EDM", 1, 15, 9, 6, None, 0.400, 0, 0, 1),
    ("Ms Jaleel", "MTL", 1, 6, 1, 5, None, 0.833, 0, 1, 0),
]

# (round_name, round_order, series_order, team_a_name, team_b_name, wins_a, wins_b, winner_name)
PLAYOFF_SERIES = [
    ("Round 1", 1, 1, "Winnipeg Jets", "Montreal Canadiens", 0, 4, "Montreal Canadiens"),
    ("Round 1", 1, 2, "Savannah Ghost Pirates", "Buffalo Sabres", 0, 4, "Buffalo Sabres"),
    ("Round 1", 1, 3, "Arizona Tropics", "Edmonton Oilers", 1, 4, "Edmonton Oilers"),
    ("Round 1", 1, 4, "San Jose Sharks", "Vancouver Canucks", 0, 2, "Vancouver Canucks"),
    ("Round 2", 2, 1, "Buffalo Sabres", "Montreal Canadiens", 3, 4, "Montreal Canadiens"),
    ("Round 2", 2, 2, "Vancouver Canucks", "Edmonton Oilers", 2, 4, "Edmonton Oilers"),
    ("Finals", 3, 1, "Edmonton Oilers", "Montreal Canadiens", 0, 5, "Montreal Canadiens"),
]


class LegacyImportCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="import-legacy-2026", description="[ONE-TIME] Import 3HL Season 2026 history from MyStatsOnline")
    @commissioner_only()
    async def import_legacy_2026(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        async with get_session() as session:
            existing = await session.scalar(select(Season).where(Season.name == "3HL Season 2026 (Legacy)"))
            if existing is not None:
                await interaction.followup.send(embed=error_embed("Already imported", "This legacy season already exists -- nothing to do."))
                return

            existing_numbers = (await session.execute(select(Season.number))).scalars().all()
            legacy_number = min(existing_numbers, default=1) - 1  # safely before any real season

            season = Season(name="3HL Season 2026 (Legacy)", number=legacy_number, is_active=False)
            session.add(season)
            await session.flush()

            teams_by_name: dict[str, Team] = {}
            for name, gp, w, l, otl, pts, gf, ga in TEAM_STANDINGS:
                team = await session.scalar(select(Team).where(Team.name.ilike(name)))
                if team is None:
                    team = Team(name=name, is_active=False)
                    session.add(team)
                    await session.flush()
                teams_by_name[name] = team

                session.add(
                    TeamSeason(
                        team_id=team.id, season_id=season.id, club_id=None,
                        wins=w, losses=l, ot_losses=otl, points=pts,
                        goals_for=gf, goals_against=ga,
                    )
                )

            players_created = 0
            for gamertag, team_abbr, pos, gp, g, a, pm, hits in SKATERS:
                team = teams_by_name.get(TEAM_ABBR_TO_NAME.get(team_abbr)) if team_abbr else None
                player = await session.scalar(select(Player).where(Player.gamertag.ilike(gamertag)))
                if player is None:
                    player = Player(gamertag=gamertag, is_goalie=False)
                    session.add(player)
                    await session.flush()
                session.add(
                    PlayerSeason(
                        player_id=player.id, season_id=season.id, team_id=team.id if team else None,
                        games_played=gp, goals=g, assists=a, points=g + a, plus_minus=pm,
                        hits=hits, pim=0, shots=0, ppg=0,
                        faceoffs_won=0, faceoffs_lost=0, takeaways=0, interceptions=0,
                        blocked_shots=0, giveaways=0, pass_attempts=0, passes_completed=0,
                        wins=0, losses=0, ot_losses=0, shots_against=0, saves=0,
                        goals_against=0, shutouts=0, minutes_played=0.0,
                    )
                )
                players_created += 1

            for gamertag, team_abbr, gp, sa, ga_, sv, gaa, svp, so, w, l in GOALIES:
                team = teams_by_name.get(TEAM_ABBR_TO_NAME.get(team_abbr)) if team_abbr else None
                player = await session.scalar(select(Player).where(Player.gamertag.ilike(gamertag)))
                if player is None:
                    player = Player(gamertag=gamertag, is_goalie=True)
                    session.add(player)
                    await session.flush()
                session.add(
                    PlayerSeason(
                        player_id=player.id, season_id=season.id, team_id=team.id if team else None,
                        games_played=gp, goals=0, assists=0, points=0, plus_minus=0,
                        hits=0, pim=0, shots=0, ppg=0,
                        faceoffs_won=0, faceoffs_lost=0, takeaways=0, interceptions=0,
                        blocked_shots=0, giveaways=0, pass_attempts=0, passes_completed=0,
                        wins=w, losses=l, ot_losses=0, shots_against=sa, saves=sv,
                        goals_against=ga_, shutouts=so, minutes_played=0.0,
                        gaa=gaa if gaa is not None else 0.0, save_pct=svp,
                    )
                )
                players_created += 1

            series_created = 0
            for round_name, round_order, series_order, team_a_name, team_b_name, wins_a, wins_b, winner_name in PLAYOFF_SERIES:
                team_a = teams_by_name.get(team_a_name)
                team_b = teams_by_name.get(team_b_name)
                winner = teams_by_name.get(winner_name)
                session.add(
                    PlayoffSeries(
                        season_id=season.id, round_name=round_name, round_order=round_order, series_order=series_order,
                        team_a_id=team_a.id if team_a else None, team_b_id=team_b.id if team_b else None,
                        wins_a=wins_a, wins_b=wins_b, winner_team_id=winner.id if winner else None,
                    )
                )
                series_created += 1

        await interaction.followup.send(
            embed=success_embed(
                "Legacy season imported",
                f"Created **3HL Season 2026 (Legacy)** with {len(TEAM_STANDINGS)} teams, {players_created} player records, "
                f"and {series_created} playoff series. This season is marked inactive -- your current season is untouched. "
                f"Use the season picker on `/league club stats` or `/league player stats` to view it.",
            )
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LegacyImportCog(bot))
