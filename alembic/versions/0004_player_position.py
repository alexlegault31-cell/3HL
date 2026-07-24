"""add position to player game stats

Revision ID: 0004_player_position
Revises: 0003_playoffs
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_player_position"
down_revision: Union[str, None] = "0003_playoffs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("player_stats", sa.Column("position", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("player_stats", "position")
