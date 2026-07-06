################################################################
FILE PATH TO TYPE ON GITHUB: bot/models/season.py
################################################################
"""
Seasons are the backbone of the "never overwrite history" requirement.
Every season-scoped table (TeamSeason, PlayerSeason, ScheduleGame, Game,
StandingsEntry, ...) carries a season_id FK pointing here. Nothing is ever
deleted or merged across seasons; a new season is just a new row + a new
set of season-scoped child rows.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import Boolean, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base, IDMixin, TimestampMixin


class Season(Base, IDMixin, TimestampMixin):
    __tablename__ = "seasons"

    number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)  # "Season 3"

    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_playoffs_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    start_date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Season #{self.number} {self.name!r} active={self.is_active}>"

===== END OF FILE, COPY UP TO HERE =====
