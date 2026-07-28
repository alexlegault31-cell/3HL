"""add game_code to teams

Revision ID: 0013_team_game_code
Revises: 0012_captured_matches
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_team_game_code"
down_revision: Union[str, None] = "0012_captured_matches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("game_code", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("teams", "game_code")
