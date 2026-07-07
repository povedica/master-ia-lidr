"""Query transform hooks for advanced retrieval (feature-061 stub)."""

from __future__ import annotations


async def transform_query(
    query: str,
    *,
    config_enabled: bool,
    settings_enabled: bool,
) -> str:
    """Optionally rewrite ``query`` before retrieval.

    Stub passthrough until decomposition/expansion is ported from the official
    ``retrieval/query_transform.py``.
    """

    del config_enabled, settings_enabled
    return query
