################################################################
FILE PATH TO TYPE ON GITHUB: bot/models/game.py
################################################################
"""
`Game` is a permanently-stored, completed result (the "we never overwrite
history" record). `GameImport` is an audit trail of the raw ChelStats
payload that produced it — kept so `/game delete` + re-import is possible,
and so disputes ("the bot got this wrong") can be debugged against the
original API response.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base, IDMixin, TimestampMixin


class Game(Base, IDMixin, TimestampMixin):
    __tablename__ = "games"

    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    schedule_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True, unique=True
    )

    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)

    home_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    away_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    went_to_overtime: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    went_to_shootout: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # The raw EASHL match id from ChelStats/ChelHead, for idempotency /
    # dedupe (a game number should never import the same match twice).
    external_match_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True, index=True)

    played_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    imported_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    imported_by_discord_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    is_forfeit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    recap_text: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    result_graphic_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    season: Mapped["Season"] = relationship()
    home_team: Mapped["Team"] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped["Team"] = relationship(foreign_keys=[away_team_id])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Game id={self.id} {self.home_score}-{self.away_score}>"


class GameImport(Base, IDMixin, TimestampMixin):
    """Audit record of exactly what was pulled from ChelStats for a Game,
    so a deletion/re-import is reproducible and disputes are debuggable."""

    __tablename__ = "game_imports"

    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="chelstats")
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    game: Mapped["Game"] = relationship()

===== END OF FILE, COPY UP TO HERE =====
