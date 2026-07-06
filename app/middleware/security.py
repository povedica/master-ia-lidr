"""Optional API-key authentication for retrieval and RAG estimate endpoints."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from app.config import Settings, get_settings

_API_KEY_HEADER = "X-API-Key"


def _verify(provided: str | None, expected: str | None) -> None:
    """Raise 401 unless ``provided`` matches the configured ``expected`` key."""
    if not expected:
        return
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": _API_KEY_HEADER},
        )


def _configured_key(settings: Settings, field_name: str) -> str | None:
    raw = getattr(settings, field_name, "")
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    return stripped or None


async def require_retrieval_key(
    x_api_key: str | None = Header(default=None, alias=_API_KEY_HEADER),
) -> None:
    """Guard ``POST /api/v1/retrieval`` when ``RETRIEVAL_API_KEY`` is set."""

    settings = get_settings()
    _verify(x_api_key, _configured_key(settings, "retrieval_api_key"))


async def require_estimate_key(
    x_api_key: str | None = Header(default=None, alias=_API_KEY_HEADER),
) -> None:
    """Guard ``POST /api/v1/estimate/rag`` when ``ESTIMATE_API_KEY`` is set."""

    settings = get_settings()
    _verify(x_api_key, _configured_key(settings, "estimate_api_key"))
