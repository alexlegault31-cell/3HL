"""add extended player stat tracking

Revision ID: 0002_extended_stats
Revises: 0001_initial
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_extended_stats"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLUMNS = [
    ("faceoffs_won", sa.Integer, 0),
    ("faceoffs_lost", sa.Integer, 0),
    ("takeaways", sa.Integer, 0),
    ("interceptions", sa.Integer, 0),
    ("blocked_shots", sa.Integer, 0),
    ("giveaways", sa.Integer, 0),
    ("pass_attempts", sa.Integer, 0),
    ("passes_completed", sa.Integer, 0),
]


def upgrade() -> None:
    for table in ("player_stats", "player_seasons"):
        for name, col_type, default in NEW_COLUMNS:
            op.add_column(table, sa.Column(name, col_type, nullable=False, server_default=str(default)))


def downgrade() -> None:
    for table in ("player_stats", "player_seasons"):
        for name, _, _ in NEW_COLUMNS:
            op.drop_column(table, name)
