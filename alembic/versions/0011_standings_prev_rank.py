"""add previous_rank to standings for trend arrows

Revision ID: 0011_standings_prev_rank
Revises: 0010_playoff_tbd
Create Date: 2026-07-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_standings_prev_rank"
down_revision: Union[str, None] = "0010_playoff_tbd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("standings", sa.Column("previous_rank", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("standings", "previous_rank")
