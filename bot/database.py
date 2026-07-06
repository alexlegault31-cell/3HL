
################################################################
FILE PATH TO TYPE ON GITHUB: bot/database.py
################################################################
"""
Database engine / session management.

We use SQLAlchemy 2.0's async ORM with asyncpg as the driver. A single
`async_sessionmaker` is shared across the whole bot; cogs/services pull a
fresh `AsyncSession` per command invocation via `get_session()`.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """
    Usage:
        async with get_session() as session:
            result = await session.execute(select(Team))
    Commits on clean exit, rolls back on exception.
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_models() -> None:
    """
    Dev convenience only — production deployments should rely on Alembic
    migrations (`alembic upgrade head`), not this. Useful for quick local
    spin-ups / tests.
    """
    from bot.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

===== END OF FILE, COPY UP TO HERE =====
