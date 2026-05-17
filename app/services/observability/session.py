"""Session id resolution for HTTP estimation requests."""

from __future__ import annotations

from uuid import uuid4

from fastapi import Request

_SESSION_HEADER_NAMES = ("X-Session-Id", "X-Session-ID")


def resolve_session_id(request: Request) -> str:
    """Prefer client session header; otherwise mint a per-request session id."""

    for header_name in _SESSION_HEADER_NAMES:
        raw = request.headers.get(header_name)
        if raw and raw.strip():
            return raw.strip()[:128]
    return f"sess_{uuid4().hex[:16]}"
