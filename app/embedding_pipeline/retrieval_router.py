"""Collection routing for advanced retrieval (feature-061 / feature-063)."""

from __future__ import annotations

from app.embedding_pipeline.collections import Collection, default_collection, match_collections


def route_collection(
    query: str,
    *,
    config_enabled: bool,
    settings_enabled: bool,
) -> str:
    """Return the primary target collection for ``query``."""

    if not (config_enabled and settings_enabled):
        return default_collection().value

    matches = match_collections(query)
    if not matches:
        return default_collection().value
    return matches[0].value
