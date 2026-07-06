
"""
Generic per-guild key/value settings store. Used for things that don't
deserve their own column/table (feature flags, last-auto-post message IDs
so we can edit-in-place instead of spamming new messages, etc).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base, IDMixin, TimestampMixin


class GuildSetting(Base, IDMixin, TimestampMixin):
    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("guild_id", "key", name="uq_setting_guild_key"),)

    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

