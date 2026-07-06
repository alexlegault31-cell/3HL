
"""
A `User` is a Discord account. Linking it to a `Player` (NHL gamertag) is
what allows automatic stat tracking via /player link.

We keep User and Player as separate entities (rather than one merged table)
because:
  * A Discord user might rename their gamertag across seasons.
  * A "player" historically existed in the league before they ever linked
    a Discord account (commissioner pre-seeds rosters).
  * It lets us support orphaned/legacy players cleanly.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base, IDMixin, TimestampMixin


class User(Base, IDMixin, TimestampMixin):
    __tablename__ = "users"

    discord_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    discord_username: Mapped[str] = mapped_column(String(64), nullable=False)

    is_commissioner: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_gm: Mapped[bool] = mapped_column(default=False, nullable=False)

    player_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    player: Mapped[Optional["Player"]] = relationship(back_populates="user")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User discord_id={self.discord_id} username={self.discord_username!r}>"

