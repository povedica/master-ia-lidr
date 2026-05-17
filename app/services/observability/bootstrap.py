"""Process-wide observability bootstrap (single adapter per process)."""

from __future__ import annotations

from app.config import Settings, get_settings
from app.services.observability.factory import build_observability_adapter
from app.services.observability.types import ObservabilityAdapter

_adapter: ObservabilityAdapter | None = None


def init_observability(settings: Settings) -> ObservabilityAdapter:
    """Construct the observability adapter once per process."""

    global _adapter
    if _adapter is None:
        _adapter = build_observability_adapter(settings)
    return _adapter


def get_observability() -> ObservabilityAdapter:
    """Return the active adapter, initializing from settings when needed."""

    if _adapter is None:
        return init_observability(get_settings())
    return _adapter


def shutdown_observability() -> None:
    """Flush pending telemetry on process shutdown."""

    if _adapter is not None:
        _adapter.flush()


def reset_observability_for_tests() -> None:
    """Clear the singleton between tests."""

    global _adapter
    _adapter = None
