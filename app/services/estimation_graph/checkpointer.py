"""Postgres checkpointer DSN helpers for the estimation graph (feature-066).

``AsyncPostgresSaver`` needs a plain libpq DSN (``postgresql://…``), not the
SQLAlchemy ``postgresql+asyncpg://`` form used by the rest of the app.
"""

from __future__ import annotations

from app.config import Settings, get_settings


def saver_conninfo(settings: Settings | None = None) -> str:
    """Derive a plain libpq DSN for ``AsyncPostgresSaver`` from ``DATABASE_URL``.

    Strips SQLAlchemy driver tokens: ``+asyncpg`` / ``+psycopg`` → plain
    ``postgresql://…``.
    """
    url = (settings or get_settings()).database_url
    if "+psycopg" in url:
        return url.replace("+psycopg", "", 1)
    if "+asyncpg" in url:
        return url.replace("+asyncpg", "", 1)
    return url
