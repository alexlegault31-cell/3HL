"""add playoff series tracking

Revision ID: 0003_playoffs
Revises: 0002_extended_stats
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_playoffs"
down_revision: Union[str, None] = "0002_extended_stats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "playoff_series",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("season_id", sa.BigInteger, sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_name", sa.String(64), nullable=False),
        sa.Column("round_order", sa.Integer, nullable=False),
        sa.Column("series_order", sa.Integer, nullable=False),
        sa.Column("team_a_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_b_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seed_a", sa.Integer, nullable=True),
        sa.Column("seed_b", sa.Integer, nullable=True),
        sa.Column("best_of", sa.Integer, nullable=False, server_default="5"),
        sa.Column("wins_a", sa.Integer, nullable=False, server_default="0"),
        sa.Column("wins_b", sa.Integer, nullable=False, server_default="0"),
        sa.Column("winner_team_id", sa.BigInteger, sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_foreign_key(
        "fk_schedules_playoff_series_id",
        "schedules",
        "playoff_series",
        ["playoff_series_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_schedules_playoff_series_id", "schedules", type_="foreignkey")
    op.drop_table("playoff_series")
