"""add time_on_attack to team_stats

Revision ID: 0009_team_toa
Revises: 0008_schedule_slots
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_team_toa"
down_revision: Union[str, None] = "0008_schedule_slots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("team_stats", sa.Column("time_on_attack", sa.Float, nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("team_stats", "time_on_attack")
