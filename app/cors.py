"""Cross-origin resource sharing for browser clients."""

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.config import Settings


def configure_cors(app: FastAPI, settings: Settings) -> None:
    """Register CORS when at least one origin is configured."""

    origins = settings.frontend_origins_list()
    if not origins:
        return

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
