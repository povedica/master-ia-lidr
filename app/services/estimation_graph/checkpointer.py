"""Postgres checkpointer wiring for the estimation graph (feature-066 / Session 13).

The graph persists state per ``thread_id`` in the same Postgres that holds pgvector
embeddings. ``AsyncPostgresSaver`` creates its own tables (``checkpoints``,
``checkpoint_writes``, ``checkpoint_blobs``) and coexists with the rest of the schema.

LangGraph's async saver is built on **psycopg3**, so it wants a plain libpq DSN
(``postgresql://…``) — not SQLAlchemy ``postgresql+asyncpg://``. ``saver_conninfo``
strips the driver token.

Human gates may pause for minutes or days. A single long-lived connection can die
during that idle window, so we back the saver with ``AsyncConnectionPool`` (validates
/ reconnects on checkout). Connections use ``autocommit``, no server-side prepares,
and ``dict_row`` — the same shape ``from_conn_string`` would set.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Mirrors AsyncPostgresSaver.from_conn_string connection shape.
_CONNECTION_KWARGS = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}
_POOL_MIN_SIZE = 1
_POOL_MAX_SIZE = 10
# Fail startup quickly when Postgres is unreachable (default pool timeout is 30s).
_POOL_OPEN_TIMEOUT_SECONDS = 5.0


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


@asynccontextmanager
async def open_checkpointer(
    settings: Settings | None = None,
) -> AsyncIterator[AsyncPostgresSaver]:
    """Open a pooled ``AsyncPostgresSaver`` over project Postgres and run ``setup()``.

    ``setup()`` is idempotent — creates checkpointer tables on first run, no-op after.
    Use as an async context manager (entered into the app ``AsyncExitStack`` in
    lifespan) so the pool closes on shutdown.
    """
    resolved = settings or get_settings()
    conninfo = saver_conninfo(resolved)
    pool = AsyncConnectionPool(
        conninfo=conninfo,
        min_size=_POOL_MIN_SIZE,
        max_size=_POOL_MAX_SIZE,
        kwargs=_CONNECTION_KWARGS,
        open=False,
        timeout=_POOL_OPEN_TIMEOUT_SECONDS,
    )
    await pool.open(wait=True)
    try:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        logger.info(
            "graph_checkpointer_ready",
            extra={"pool_max": _POOL_MAX_SIZE},
        )
        yield checkpointer
    finally:
        await pool.close()
