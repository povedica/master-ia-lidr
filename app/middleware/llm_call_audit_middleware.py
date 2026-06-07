"""HTTP middleware that captures API route context for LLM call audit JSON."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

from app.services.llm_call_audit import (
    reset_llm_call_audit,
    restore_llm_call_audit,
    set_llm_call_api_endpoint,
)


async def llm_call_audit_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Attach endpoint metadata for optional ``LLM_CALL_PERSIST_ENABLED`` dumps."""

    token = reset_llm_call_audit()
    set_llm_call_api_endpoint(method=request.method, path=request.url.path)
    try:
        return await call_next(request)
    finally:
        restore_llm_call_audit(token)
