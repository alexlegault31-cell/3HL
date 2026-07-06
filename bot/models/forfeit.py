
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base, IDMixin, TimestampMixin


class Forfeit(Base, IDMixin, TimestampMixin):
    """Manually recorded forfeit, entered via /game ffw. Produces a Game
    row (is_forfeit=True) so it shows up everywhere a normal result does,
    plus this row for the forfeit-specific metadata (reason, who entered it)."""

    __tablename__ = "forfeits"

    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    schedule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False)

    winning_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    losing_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)

    winning_score: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    losing_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    entered_by_discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entered_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    season: Mapped["Season"] = relationship()
    game: Mapped["Game"] = relationship()
    winning_team: Mapped["Team"] = relationship(foreign_keys=[winning_team_id])
    losing_team: Mapped["Team"] = relationship(foreign_keys=[losing_team_id])

