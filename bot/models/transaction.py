################################################################
FILE PATH TO TYPE ON GITHUB: bot/models/transaction.py
################################################################
from __future__ import annotations

import datetime as dt
import enum
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base, IDMixin, TimestampMixin


class TransactionType(str, enum.Enum):
    SIGNING = "signing"
    RELEASE = "release"
    TRADE = "trade"
    CALLUP = "callup"
    DEMOTION = "demotion"
    SUSPENSION = "suspension"
    RETIREMENT = "retirement"


class Transaction(Base, IDMixin, TimestampMixin):
    """Roster moves / GM transaction log -- powers /team history and gives
    commissioners an audit trail independent of Discord chat scrollback."""

    __tablename__ = "transactions"

    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False)

    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType, name="transaction_type"), nullable=False)

    from_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    to_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    executed_by_discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    executed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    season: Mapped["Season"] = relationship()
    player: Mapped["Player"] = relationship()
    from_team: Mapped[Optional["Team"]] = relationship(foreign_keys=[from_team_id])
    to_team: Mapped[Optional["Team"]] = relationship(foreign_keys=[to_team_id])

===== END OF FILE, COPY UP TO HERE =====
