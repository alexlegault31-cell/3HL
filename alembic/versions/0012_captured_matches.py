"""add captured_matches for background EA match capture

Revision ID: 0012_captured_matches
Revises: 0011_standings_prev_rank
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_captured_matches"
down_revision: Union[str, None] = "0011_standings_prev_rank"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "captured_matches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("match_id", sa.String(128), nullable=False),
        sa.Column("club_id_a", sa.BigInteger, nullable=False),
        sa.Column("club_id_b", sa.BigInteger, nullable=False),
        sa.Column("ea_timestamp", sa.Integer, nullable=False),
        sa.Column("raw_payload", sa.JSON, nullable=False),
        sa.UniqueConstraint("match_id", name="uq_captured_match_id"),
    )
    op.create_index("ix_captured_matches_club_a", "captured_matches", ["club_id_a"])
    op.create_index("ix_captured_matches_club_b", "captured_matches", ["club_id_b"])


def downgrade() -> None:
    op.drop_index("ix_captured_matches_club_b", table_name="captured_matches")
    op.drop_index("ix_captured_matches_club_a", table_name="captured_matches")
    op.drop_table("captured_matches")
