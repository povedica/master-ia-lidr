"""FastAPI application entrypoint."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.cors import configure_cors
from app.middleware.llm_call_audit_middleware import llm_call_audit_middleware
from app.routers import embeddings, estimations, estimations_v2, retrieval_debug, search, sessions
from app.services.llm_chain import build_provider_chain
from app.services.observability.bootstrap import init_observability, shutdown_observability

_log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, _log_level.upper(), logging.INFO),
    format="%(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log safe startup context (no secrets)."""

    settings = get_settings()
    providers = build_provider_chain(settings)
    provider_names = [provider.name for provider in providers]
    logging.getLogger(__name__).info(
        "chain_built",
        extra={
            "providers": provider_names,
            "static_fallback_enabled": settings.static_fallback_enabled,
        },
    )
    logging.getLogger(__name__).info(
        "app_startup",
        extra={"app_env": settings.app_env, "providers": provider_names},
    )
    observability = init_observability(settings)
    logging.getLogger(__name__).info(
        "observability_initialized",
        extra={
            "event": "observability_initialized",
            "export_active": settings.observability_export_active(),
            "adapter": type(observability).__name__,
        },
    )
    yield
    shutdown_observability()


app = FastAPI(
    title="Estimador CAG",
    description=(
        "Minimal Context-Augmented Generation API: few-shot estimation examples "
        "in the system prompt plus structured project context from the client."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

configure_cors(app, get_settings())
app.middleware("http")(llm_call_audit_middleware)

app.include_router(estimations.router, prefix="/api/v1")
app.include_router(estimations_v2.router, prefix="/api/v2")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(embeddings.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(retrieval_debug.router, prefix="/api/v1")


@app.get("/")
def read_root() -> dict[str, str]:
    """Human-friendly entry when opening the base URL in a browser."""

    return {
        "service": "Estimador CAG",
        "docs": "/docs",
        "health": "/health",
        "estimate": "POST /api/v1/estimate",
        "estimate_stream": "POST /api/v1/estimate/stream",
        "estimate_structured": "POST /api/v2/estimate",
        "sessions": "POST /api/v1/sessions",
        "session_estimate": "POST /api/v1/sessions/{session_id}/estimate",
        "embeddings": "POST /api/v1/embeddings/ingest",
        "search": "POST /api/v1/search",
        "retrieval_debug": "POST /api/v1/retrieval-debug",
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for orchestrators and local checks."""

    return {"status": "ok"}
