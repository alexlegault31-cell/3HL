"""make playoff_series team_a_id/team_b_id nullable for TBD slots

Revision ID: 0010_playoff_tbd
Revises: 0009_team_toa
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_playoff_tbd"
down_revision: Union[str, None] = "0009_team_toa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("playoff_series", "team_a_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("playoff_series", "team_b_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("playoff_series", "team_a_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("playoff_series", "team_b_id", existing_type=sa.Integer(), nullable=False)
