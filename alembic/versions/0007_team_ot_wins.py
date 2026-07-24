"""add ot_wins subset counter to team_seasons

Revision ID: 0007_team_ot_wins
Revises: 0006_goalie_season_stats
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_team_ot_wins"
down_revision: Union[str, None] = "0006_goalie_season_stats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("team_seasons", sa.Column("ot_wins", sa.Integer, nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("team_seasons", "ot_wins")
