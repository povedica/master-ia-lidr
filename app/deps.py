"""Shared FastAPI dependencies."""

from __future__ import annotations

from functools import lru_cache
from uuid import uuid4

from starlette.requests import Request

from app.config import get_settings
from app.services.estimation_graph.activity import GraphActivityLog


def get_request_id(request: Request) -> str:
    """Return the correlation id bound by the request-id middleware."""

    bound = getattr(request.state, "request_id", None)
    if isinstance(bound, str) and bound:
        return bound
    return str(uuid4())


@lru_cache
def get_graph_activity() -> GraphActivityLog:
    """Redis-backed (or in-process) per-run activity log for the live graph panel."""

    return GraphActivityLog.from_settings(get_settings())
