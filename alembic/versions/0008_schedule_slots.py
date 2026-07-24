"""add day_of_week/game_time slot labels to schedules

Revision ID: 0008_schedule_slots
Revises: 0007_team_ot_wins
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_schedule_slots"
down_revision: Union[str, None] = "0007_team_ot_wins"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("schedules", sa.Column("day_of_week", sa.String(length=10), nullable=True))
    op.add_column("schedules", sa.Column("game_time", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("schedules", "day_of_week")
    op.drop_column("schedules", "game_time")
