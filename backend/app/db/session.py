"""Async SQLAlchemy engine and session dependency.

One engine per process holds a connection pool; each request borrows a
session (and therefore a pooled connection) and returns it when done.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    # Detects connections killed by the DB/network before handing them out.
    pool_pre_ping=True,
)

# expire_on_commit=False: objects stay readable after commit, so we can
# serialize them in the response without triggering a lazy reload.
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session that is always closed afterwards."""
    async with SessionLocal() as session:
        yield session
