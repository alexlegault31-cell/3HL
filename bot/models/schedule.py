
"""
The schedule is the *source of truth* for the league. A ScheduleGame is
created by the commissioner ahead of time (bulk import or manual) with a
human-friendly, season-scoped `game_number` (what /entergame <N> refers
to). It is only ever linked to a `Game` once stats have actually been
imported for it — until then, status stays "scheduled"/"pending".
"""
from __future__ import annotations

import datetime as dt
import enum
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base, IDMixin, TimestampMixin


class ScheduleStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    PLAYED = "played"
    FORFEITED = "forfeited"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class ScheduleGame(Base, IDMixin, TimestampMixin):
    __tablename__ = "schedules"
    __table_args__ = (UniqueConstraint("season_id", "game_number", name="uq_schedule_season_gamenum"),)

    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    game_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    is_playoffs: Mapped[bool] = mapped_column(default=False, nullable=False)
    playoff_round: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    playoff_series_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)

    scheduled_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[ScheduleStatus] = mapped_column(
        Enum(ScheduleStatus, name="schedule_status"), default=ScheduleStatus.SCHEDULED, nullable=False
    )

    # Set once a Game has been imported / forfeit recorded against this slot.
    game_id: Mapped[Optional[int]] = mapped_column(ForeignKey("games.id", ondelete="SET NULL"), nullable=True)

    season: Mapped["Season"] = relationship()
    home_team: Mapped["Team"] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped["Team"] = relationship(foreign_keys=[away_team_id])
    game: Mapped[Optional["Game"]] = relationship(foreign_keys=[game_id])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ScheduleGame #{self.game_number} season={self.season_id} status={self.status}>"

