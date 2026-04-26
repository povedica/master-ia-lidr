"""FastAPI application entrypoint."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.routers import estimations

_log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, _log_level.upper(), logging.INFO),
    format="%(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log safe startup context (no secrets)."""

    settings = get_settings()
    logging.getLogger(__name__).info(
        "app_startup",
        extra={"app_env": settings.app_env, "provider": settings.llm_provider},
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


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for orchestrators and local checks."""

    return {"status": "ok"}
