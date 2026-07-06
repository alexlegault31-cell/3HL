
"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    schedule_status = sa.Enum(
        "scheduled", "played", "forfeited", "postponed", "cancelled", name="schedule_status"
    )
    transaction_type = sa.Enum(
        "signing", "release", "trade", "callup", "demotion", "suspension", "retirement",
        name="transaction_type",
    )

    op.create_table(
        "seasons",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("number", sa.Integer, nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, default=False),
        sa.Column("is_playoffs_active", sa.Boolean, nullable=False, default=False),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
    )

    op.create_table(
        "teams",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("abbreviation", sa.String(8), nullable=True),
        sa.Column("logo_url", sa.String(512), nullable=True),
        sa.Column("primary_color", sa.String(7), nullable=True),
        sa.Column("secondary_color", sa.String(7), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
    )

    op.create_table(
        "players",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("gamertag", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("external_player_id", sa.String(64), nullable=True, index=True),
        sa.Column("is_goalie", sa.Boolean, nullable=False, default=False),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("discord_id", sa.BigInteger, nullable=False, unique=True, index=True),
        sa.Column("discord_username", sa.String(64), nullable=False),
        sa.Column("is_commissioner", sa.Boolean, nullable=False, default=False),
        sa.Column("is_gm", sa.Boolean, nullable=False, default=False),
        sa.Column("player_id", sa.BigInteger, sa.ForeignKey("players.id", ondelete="SET NULL"), nullable=True, unique=True),
    )

    op.create_table(
        "team_seasons",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", sa.BigInteger, sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_id", sa.BigInteger, nullable=True, index=True),
        sa.Column("club_name_cache", sa.String(128), nullable=True),
        sa.Column("wins", sa.Integer, nullable=False, default=0),
        sa.Column("losses", sa.Integer, nullable=False, default=0),
        sa.Column("ot_losses", sa.Integer, nullable=False, default=0),
        sa.Column("points", sa.Integer, nullable=False, default=0),
        sa.Column("goals_for", sa.Integer, nullable=False, default=0),
        sa.Column("goals_against", sa.Integer, nullable=False, default=0),
        sa.Column("streak_type", sa.String(1), nullable=True),
        sa.Column("streak_count", sa.Integer, nullable=False, default=0),
        sa.Column("last_10", sa.String(10), nullable=True),
        sa.UniqueConstraint("team_id", "season_id", name="uq_team_season"),
        sa.UniqueConstraint("club_id", "season_id", name="uq_club_id_season"),
    )

    op.create_table(
        "player_team_links",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("player_id", sa.BigInteger, sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", sa.BigInteger, sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("effective_from", sa.Date, nullable=True),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("is_current", sa.Boolean, nullable=False, default=True),
        sa.UniqueConstraint("player_id", "season_id", "team_id", name="uq_player_team_season"),
    )

    op.create_table(
        "player_seasons",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("player_id", sa.BigInteger, sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", sa.BigInteger, sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("games_played", sa.Integer, nullable=False, default=0),
        sa.Column("goals", sa.Integer, nullable=False, default=0),
        sa.Column("assists", sa.Integer, nullable=False, default=0),
        sa.Column("points", sa.Integer, nullable=False, default=0),
        sa.Column("plus_minus", sa.Integer, nullable=False, default=0),
        sa.Column("hits", sa.Integer, nullable=False, default=0),
        sa.Column("pim", sa.Integer, nullable=False, default=0),
        sa.Column("shots", sa.Integer, nullable=False, default=0),
        sa.Column("ppg", sa.Integer, nullable=False, default=0),
        sa.Column("wins", sa.Integer, nullable=False, default=0),
        sa.Column("losses", sa.Integer, nullable=False, default=0),
        sa.Column("ot_losses", sa.Integer, nullable=False, default=0),
        sa.Column("shots_against", sa.Integer, nullable=False, default=0),
        sa.Column("saves", sa.Integer, nullable=False, default=0),
        sa.Column("goals_against", sa.Integer, nullable=False, default=0),
        sa.Column("shutouts", sa.Integer, nullable=False, default=0),
        sa.Column("minutes_played", sa.Float, nullable=False, default=0.0),
        sa.UniqueConstraint("player_id", "season_id", name="uq_player_season"),
    )

    op.create_table(
        "schedules",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("season_id", sa.BigInteger, sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("game_number", sa.Integer, nullable=False, index=True),
        sa.Column("week", sa.Integer, nullable=True, index=True),
        sa.Column("is_playoffs", sa.Boolean, nullable=False, default=False),
        sa.Column("playoff_round", sa.String(32), nullable=True),
        sa.Column("playoff_series_id", sa.Integer, nullable=True),
        sa.Column("home_team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("away_team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", schedule_status, nullable=False, server_default="scheduled"),
        sa.Column("game_id", sa.BigInteger, nullable=True),  # FK added after games table exists
        sa.UniqueConstraint("season_id", "game_number", name="uq_schedule_season_gamenum"),
    )

    op.create_table(
        "games",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("season_id", sa.BigInteger, sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schedule_id", sa.BigInteger, sa.ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True, unique=True),
        sa.Column("home_team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("away_team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("home_score", sa.Integer, nullable=False, default=0),
        sa.Column("away_score", sa.Integer, nullable=False, default=0),
        sa.Column("went_to_overtime", sa.Boolean, nullable=False, default=False),
        sa.Column("went_to_shootout", sa.Boolean, nullable=False, default=False),
        sa.Column("external_match_id", sa.String(128), nullable=True, unique=True, index=True),
        sa.Column("played_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_by_discord_id", sa.BigInteger, nullable=True),
        sa.Column("is_forfeit", sa.Boolean, nullable=False, default=False),
        sa.Column("recap_text", sa.String(2000), nullable=True),
        sa.Column("result_graphic_path", sa.String(512), nullable=True),
    )

    op.create_foreign_key(
        "fk_schedules_game_id", "schedules", "games", ["game_id"], ["id"], ondelete="SET NULL"
    )

    op.create_table(
        "game_imports",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("game_id", sa.BigInteger, sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, default="chelstats"),
        sa.Column("raw_payload", sa.JSON, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "player_stats",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("game_id", sa.BigInteger, sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("player_id", sa.BigInteger, sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", sa.BigInteger, sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("goals", sa.Integer, nullable=False, default=0),
        sa.Column("assists", sa.Integer, nullable=False, default=0),
        sa.Column("points", sa.Integer, nullable=False, default=0),
        sa.Column("plus_minus", sa.Integer, nullable=False, default=0),
        sa.Column("hits", sa.Integer, nullable=False, default=0),
        sa.Column("pim", sa.Integer, nullable=False, default=0),
        sa.Column("shots", sa.Integer, nullable=False, default=0),
        sa.Column("ppg", sa.Integer, nullable=False, default=0),
    )

    op.create_table(
        "goalie_stats",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("game_id", sa.BigInteger, sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("player_id", sa.BigInteger, sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", sa.BigInteger, sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("result", sa.Integer, nullable=False, default=0),
        sa.Column("shots_against", sa.Integer, nullable=False, default=0),
        sa.Column("saves", sa.Integer, nullable=False, default=0),
        sa.Column("goals_against", sa.Integer, nullable=False, default=0),
        sa.Column("minutes_played", sa.Float, nullable=False, default=0.0),
        sa.Column("shutout", sa.Boolean, nullable=False, default=False),
    )

    op.create_table(
        "team_stats",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("game_id", sa.BigInteger, sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", sa.BigInteger, sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("goals", sa.Integer, nullable=False, default=0),
        sa.Column("shots", sa.Integer, nullable=False, default=0),
        sa.Column("hits", sa.Integer, nullable=False, default=0),
        sa.Column("pim", sa.Integer, nullable=False, default=0),
        sa.Column("powerplay_goals", sa.Integer, nullable=False, default=0),
        sa.Column("powerplay_opportunities", sa.Integer, nullable=False, default=0),
    )

    op.create_table(
        "standings",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("season_id", sa.BigInteger, sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("wins", sa.Integer, nullable=False, default=0),
        sa.Column("losses", sa.Integer, nullable=False, default=0),
        sa.Column("ot_losses", sa.Integer, nullable=False, default=0),
        sa.Column("points", sa.Integer, nullable=False, default=0),
        sa.Column("goals_for", sa.Integer, nullable=False, default=0),
        sa.Column("goals_against", sa.Integer, nullable=False, default=0),
        sa.Column("goal_diff", sa.Integer, nullable=False, default=0),
        sa.Column("streak", sa.String(8), nullable=False, default="-"),
        sa.UniqueConstraint("season_id", "team_id", name="uq_standings_season_team"),
    )

    op.create_table(
        "forfeits",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("season_id", sa.BigInteger, sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schedule_id", sa.BigInteger, sa.ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True),
        sa.Column("game_id", sa.BigInteger, sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("winning_team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("losing_team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("winning_score", sa.Integer, nullable=False, default=1),
        sa.Column("losing_score", sa.Integer, nullable=False, default=0),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("entered_by_discord_id", sa.BigInteger, nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "awards",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("key", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("icon_emoji", sa.String(32), nullable=True),
    )

    op.create_table(
        "award_winners",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("award_id", sa.BigInteger, sa.ForeignKey("awards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", sa.BigInteger, sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", sa.BigInteger, sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("awarded_by_discord_id", sa.BigInteger, nullable=True),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("season_id", sa.BigInteger, sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", sa.BigInteger, sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", transaction_type, nullable=False),
        sa.Column("from_team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("executed_by_discord_id", sa.BigInteger, nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "settings",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("guild_id", sa.BigInteger, nullable=False, index=True),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value", sa.String(2000), nullable=True),
        sa.UniqueConstraint("guild_id", "key", name="uq_setting_guild_key"),
    )


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_table("transactions")
    op.drop_table("award_winners")
    op.drop_table("awards")
    op.drop_table("forfeits")
    op.drop_table("standings")
    op.drop_table("team_stats")
    op.drop_table("goalie_stats")
    op.drop_table("player_stats")
    op.drop_table("game_imports")
    op.drop_constraint("fk_schedules_game_id", "schedules", type_="foreignkey")
    op.drop_table("games")
    op.drop_table("schedules")
    op.drop_table("player_seasons")
    op.drop_table("player_team_links")
    op.drop_table("team_seasons")
    op.drop_table("users")
    op.drop_table("players")
    op.drop_table("teams")
    op.drop_table("seasons")
    sa.Enum(name="schedule_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="transaction_type").drop(op.get_bind(), checkfirst=True)
