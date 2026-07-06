"""Global request correlation id middleware."""

from __future__ import annotations

import contextvars
import logging
from collections.abc import Awaitable, Callable
from uuid import uuid4

from starlette.requests import Request
from starlette.responses import Response

_request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)


class RequestIdLogFilter(logging.Filter):
    """Attach the active request id to stdlib log records when present."""

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = _request_id_ctx.get()
        if request_id and not hasattr(record, "request_id"):
            record.request_id = request_id  # type: ignore[attr-defined]
        return True


def install_request_id_logging() -> None:
    """Register the request-id filter on the root logger once at startup."""

    root = logging.getLogger()
    if any(isinstance(existing, RequestIdLogFilter) for existing in root.filters):
        return
    root.addFilter(RequestIdLogFilter())


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Bind a correlation id per request and echo it on ``X-Request-ID``."""

    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    token = _request_id_ctx.set(request_id)
    try:
        response = await call_next(request)
    finally:
        _request_id_ctx.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response
