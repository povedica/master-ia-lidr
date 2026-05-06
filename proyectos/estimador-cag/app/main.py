"""FastAPI application entrypoint."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.routers import estimations
from app.services.llm_chain import build_provider_chain

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
    yield


app = FastAPI(
    title="Estimador CAG",
    description=(
        "Minimal Context-Augmented Generation API: few-shot estimation examples "
        "in the system prompt plus a meeting transcription from the client."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(estimations.router, prefix="/api/v1")


@app.get("/")
def read_root() -> dict[str, str]:
    """Human-friendly entry when opening the base URL in a browser."""

    return {
        "service": "Estimador CAG",
        "docs": "/docs",
        "health": "/health",
        "estimate": "POST /api/v1/estimate",
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for orchestrators and local checks."""

    return {"status": "ok"}
