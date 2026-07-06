
from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base, IDMixin, TimestampMixin


class Award(Base, IDMixin, TimestampMixin):
    """Award *type* definitions, e.g. MVP / Best Goalie / Best Defenseman /
    Rookie of the Year. Kept as data (not an enum) so commissioners can add
    new award categories via /award create without a migration."""

    __tablename__ = "awards"

    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # "mvp"
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)  # "Most Valuable Player"
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    icon_emoji: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


class AwardWinner(Base, IDMixin, TimestampMixin):
    __tablename__ = "award_winners"

    award_id: Mapped[int] = mapped_column(ForeignKey("awards.id", ondelete="CASCADE"), nullable=False)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)

    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    awarded_by_discord_id: Mapped[Optional[int]] = mapped_column(nullable=True)

    award: Mapped["Award"] = relationship()
    season: Mapped["Season"] = relationship()
    player: Mapped["Player"] = relationship()
    team: Mapped[Optional["Team"]] = relationship()

