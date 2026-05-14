"""OpenAI embedding adapter for semantic cache."""

from __future__ import annotations

from openai import AsyncOpenAI

from app.config import Settings


class OpenAIEmbeddingProvider:
    """Production embedding path using the OpenAI embeddings API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = settings.semantic_cache_embedding_model.strip() or "text-embedding-3-small"
        self._timeout = float(settings.semantic_cache_embedding_timeout_seconds)

    async def embed(self, text: str) -> list[float]:
        key = self._settings.openai_api_key.strip()
        if not key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings")
        client = AsyncOpenAI(api_key=key, timeout=self._timeout)
        safe_input = text if len(text) <= 32_000 else text[:32_000]
        response = await client.embeddings.create(model=self._model, input=safe_input)
        vec = response.data[0].embedding
        return [float(x) for x in vec]
