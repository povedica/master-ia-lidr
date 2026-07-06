"""Shared FastAPI dependencies."""

from __future__ import annotations

from uuid import uuid4

from starlette.requests import Request


def get_request_id(request: Request) -> str:
    """Return the correlation id bound by the request-id middleware."""

    bound = getattr(request.state, "request_id", None)
    if isinstance(bound, str) and bound:
        return bound
    return str(uuid4())
