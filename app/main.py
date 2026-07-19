"""FastAPI application entrypoint."""

import logging
import os
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.cors import configure_cors
from app.middleware.llm_call_audit_middleware import llm_call_audit_middleware
from app.middleware.rate_limiting import limiter, rate_limit_exceeded_handler
from app.middleware.request_id import install_request_id_logging, request_id_middleware
from app.routers import (
    agent_estimations,
    embeddings,
    estimate_graph,
    estimations,
    estimations_v2,
    rag_estimations,
    rag_stages,
    rag_task_hours,
    retrieval,
    retrieval_advanced,
    retrieval_debug,
    runtime_config,
    search,
    sessions,
)
from app.services.llm_chain import build_provider_chain
from app.services.observability.bootstrap import init_observability, shutdown_observability

_log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, _log_level.upper(), logging.INFO),
    format="%(levelname)s %(name)s %(message)s",
)
install_request_id_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log safe startup context (no secrets) and optionally wire the estimation graph."""

    settings = get_settings()
    providers = build_provider_chain(settings)
    provider_names = [provider.name for provider in providers]
    logger.info(
        "chain_built",
        extra={
            "providers": provider_names,
            "static_fallback_enabled": settings.static_fallback_enabled,
        },
    )
    logger.info(
        "app_startup",
        extra={"app_env": settings.app_env, "providers": provider_names},
    )
    observability = init_observability(settings)
    logger.info(
        "observability_initialized",
        extra={
            "event": "observability_initialized",
            "export_active": settings.observability_export_active(),
            "adapter": type(observability).__name__,
        },
    )

    # Session 13: Postgres checkpointer + compiled graph. Held open for the app
    # lifetime via AsyncExitStack. Failure (e.g. Postgres down) leaves
    # app.state.graph = None so graph routes can 503 without taking down /health
    # or unrelated routers.
    app.state.graph = None
    app.state._graph_stack = AsyncExitStack()
    if not settings.database_url.strip():
        logger.info(
            "graph_init_skipped",
            extra={"reason": "database_url_empty"},
        )
    else:
        try:
            from app.services.estimation_graph.build import build_graph
            from app.services.estimation_graph.checkpointer import open_checkpointer

            checkpointer = await app.state._graph_stack.enter_async_context(
                open_checkpointer(settings)
            )
            app.state.graph = build_graph(checkpointer)
            logger.info("graph_ready")
        except Exception as exc:  # noqa: BLE001 — graph is optional infrastructure
            logger.error(
                "graph_init_failed",
                extra={"error": str(exc)[:400]},
            )

    yield
    await app.state._graph_stack.aclose()
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
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.middleware("http")(request_id_middleware)
app.middleware("http")(llm_call_audit_middleware)

app.include_router(estimations.router, prefix="/api/v1")
app.include_router(estimations_v2.router, prefix="/api/v2")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(embeddings.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(retrieval_debug.router, prefix="/api/v1")
app.include_router(retrieval.router, prefix="/api/v1")
app.include_router(retrieval_advanced.router, prefix="/api/v1")
app.include_router(rag_estimations.router, prefix="/api/v1")
app.include_router(agent_estimations.router, prefix="/api/v1")
app.include_router(estimate_graph.router, prefix="/api/v1")
app.include_router(rag_stages.router, prefix="/api/v1")
app.include_router(rag_task_hours.router, prefix="/api/v1")
app.include_router(runtime_config.router, prefix="/api/v1")


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
        "retrieval": "POST /api/v1/retrieval",
        "retrieval_advanced": "POST /api/v1/retrieval/advanced",
        "estimate_rag": "POST /api/v1/estimate/rag",
        "estimate_agent": "POST /api/v1/estimate/agent",
        "estimate_graph": "POST /api/v1/estimate/graph",
        "estimate_graph_resume": "POST /api/v1/estimate/graph/{id}/resume",
        "estimate_graph_state": "GET /api/v1/estimate/graph/{id}/state",
        "retrieval_debug": "POST /api/v1/retrieval-debug",
        "config_retrieval": "GET/PUT /api/v1/config/retrieval",
        "config_models": "GET/PUT /api/v1/config/models",
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for orchestrators and local checks."""

    return {"status": "ok"}
