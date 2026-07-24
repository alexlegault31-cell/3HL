"""add toi/time-with-puck for skaters, poke checks/desperation saves for goalies

Revision ID: 0005_more_stats
Revises: 0004_player_position
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_more_stats"
down_revision: Union[str, None] = "0004_player_position"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("player_stats", sa.Column("minutes_played", sa.Float, nullable=False, server_default="0"))
    op.add_column("player_stats", sa.Column("time_with_puck", sa.Float, nullable=False, server_default="0"))
    op.add_column("goalie_stats", sa.Column("poke_checks", sa.Integer, nullable=False, server_default="0"))
    op.add_column("goalie_stats", sa.Column("desperation_saves", sa.Integer, nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("player_stats", "minutes_played")
    op.drop_column("player_stats", "time_with_puck")
    op.drop_column("goalie_stats", "poke_checks")
    op.drop_column("goalie_stats", "desperation_saves")
