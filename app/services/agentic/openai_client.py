"""Dedicated AsyncOpenAI client for the agentic Responses API path."""

from __future__ import annotations

from openai import AsyncOpenAI

from app.config import Settings


def get_async_openai_client(settings: Settings) -> AsyncOpenAI | None:
    """Return an AsyncOpenAI client when OPENAI_API_KEY is configured."""
    key = settings.openai_api_key.strip()
    if not key:
        return None
    return AsyncOpenAI(api_key=key, timeout=settings.openai_timeout_seconds)
