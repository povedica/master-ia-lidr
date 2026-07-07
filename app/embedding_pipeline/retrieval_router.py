"""Collection routing for advanced retrieval (feature-061 stub until feature-063)."""

from __future__ import annotations

_DEFAULT_COLLECTION = "budgets"


def route_collection(
    query: str,
    *,
    config_enabled: bool,
    settings_enabled: bool,
) -> str:
    """Return the target collection for ``query``.

    Stub: always ``budgets`` until multi-index routing lands in feature-063.
    """

    del query
    if config_enabled and settings_enabled:
        return _DEFAULT_COLLECTION
    return _DEFAULT_COLLECTION
