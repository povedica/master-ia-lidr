"""Async SQLAlchemy engine and session setup for Postgres persistence."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from fastapi import HTTPException, status

from app.config import Settings, get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    """Build an async engine from ``settings.database_url``."""

    resolved = settings or get_settings()
    if not resolved.database_url.strip():
        raise ValueError("DATABASE_URL is required to create the async engine")
    return create_async_engine(resolved.database_url, echo=False)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a configured async session factory."""

    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield a session with commit on success and rollback on error."""

    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    """Return a cached async session factory for the configured database."""

    global _engine, _session_factory
    if _session_factory is None:
        resolved = settings or get_settings()
        _engine = create_engine(resolved)
        _session_factory = create_session_factory(_engine)
    return _session_factory


def reset_session_factory() -> None:
    """Clear cached engine/factory (for tests)."""

    global _engine, _session_factory
    _engine = None
    _session_factory = None


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields one request-scoped async session."""

    settings = get_settings()
    if not settings.database_url.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured.",
        )
    factory = get_session_factory(settings)
    session = factory()
    try:
        yield session
    finally:
        await session.close()
