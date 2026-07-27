"""
Archives raw EA match data the moment the background capture loop sees
it -- independent of whether/when it's later processed into an official
Game via /league admin submit-game. This is what protects against EA's
match-history API only ever returning a club's last ~5 games: once a
match is captured here, it's safe even if it later scrolls out of EA's
own live window.
"""
from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base, IDMixin, TimestampMixin


class CapturedMatch(Base, IDMixin, TimestampMixin):
    __tablename__ = "captured_matches"
    __table_args__ = (UniqueConstraint("match_id", name="uq_captured_match_id"),)

    match_id: Mapped[str] = mapped_column(String(128), nullable=False)
    club_id_a: Mapped[int] = mapped_column(BigInteger, nullable=False)
    club_id_b: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ea_timestamp: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
