"""add poke checks/desperation saves season totals to player_seasons

Revision ID: 0006_goalie_season_stats
Revises: 0005_more_stats
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_goalie_season_stats"
down_revision: Union[str, None] = "0005_more_stats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("player_seasons", sa.Column("poke_checks", sa.Integer, nullable=False, server_default="0"))
    op.add_column("player_seasons", sa.Column("desperation_saves", sa.Integer, nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("player_seasons", "poke_checks")
    op.drop_column("player_seasons", "desperation_saves")
