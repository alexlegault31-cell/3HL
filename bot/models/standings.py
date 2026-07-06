################################################################
FILE PATH TO TYPE ON GITHUB: bot/models/standings.py
################################################################
"""
StandingsEntry is technically derivable from TeamSeason, but we materialize
it as its own table so that:
  1. `/standings season:N` for a *past* season is a cheap, stable read even
     if we later change how standings are computed.
  2. We can store rank explicitly (with tiebreakers applied) instead of
     recomputing tiebreak logic on every read.
It is recomputed (not incrementally patched) every time a game/forfeit is
entered or deleted, by `services/standings_service.py`.
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base, IDMixin, TimestampMixin


class StandingsEntry(Base, IDMixin, TimestampMixin):
    __tablename__ = "standings"
    __table_args__ = (UniqueConstraint("season_id", "team_id", name="uq_standings_season_team"),)

    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)

    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ot_losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_for: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_against: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goal_diff: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    streak: Mapped[str] = mapped_column(String(8), default="-", nullable=False)

    season: Mapped["Season"] = relationship()
    team: Mapped["Team"] = relationship()

===== END OF FILE, COPY UP TO HERE =====
