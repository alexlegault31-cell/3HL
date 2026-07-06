
"""
Shared SQLAlchemy declarative base + reusable mixins.

Design notes
------------
* Every table has a surrogate BIGINT identity PK (`id`), even though some
  tables (e.g. PlayerTeamLink) could use a composite key — this keeps FKs
  simple and migrations painless.
* `TimestampMixin` gives every row `created_at` / `updated_at` for free,
  which matters a lot for a system whose entire job is "never overwrite
  history" — if something looks wrong, we can tell when it was written.
* Season-scoped tables all carry an explicit `season_id` FK rather than
  relying on "current season" state anywhere, which is what lets
  `/player stats season:1` and `/player stats season:2` coexist forever.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class IDMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

