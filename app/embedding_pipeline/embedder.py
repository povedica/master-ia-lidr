"""OpenAI embedder for pipeline chunks with batching, retry, and cost tracking."""

from __future__ import annotations

import asyncio
import logging
import math
from time import perf_counter

from openai import AsyncOpenAI, RateLimitError

from app.config import Settings
from app.embedding_pipeline.schemas import Chunk, EmbeddedChunk

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
COST_PER_MILLION_TOKENS = 0.02
DEFAULT_BATCH_SIZE = 100
EXPECTED_EMBEDDING_DIM = 1536
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (1, 2, 4)


class OpenAIEmbedder:
    """Async OpenAI embeddings client for the embedding pipeline ingest path.

    After ``embed_many``, read ``last_total_tokens`` and ``last_cost_usd`` for
    ingest stats. Cost uses ``COST_PER_MILLION_TOKENS`` as an indicative estimate.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = (
            settings.embedding_pipeline_model.strip() or EMBEDDING_MODEL
        )
        self._batch_size = settings.embedding_pipeline_batch_size
        self._timeout = float(settings.openai_timeout_seconds)
        self.last_total_tokens: int = 0
        self.last_cost_usd: float = 0.0

    def _require_api_key(self) -> str:
        key = self._settings.openai_api_key.strip()
        if not key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings")
        return key

    def _validate_vectors(self, vectors: list[list[float]]) -> list[list[float]]:
        validated: list[list[float]] = []
        for vector in vectors:
            if len(vector) != EXPECTED_EMBEDDING_DIM:
                raise ValueError(
                    f"Expected embedding dimension {EXPECTED_EMBEDDING_DIM}, "
                    f"got {len(vector)}"
                )
            floats = [float(x) for x in vector]
            if not all(math.isfinite(x) for x in floats):
                raise ValueError("Embedding contains non-finite values")
            validated.append(floats)
        return validated

    async def _embed_batch(
        self,
        texts: list[str],
        *,
        batch_index: int,
        batch_tokens: int,
    ) -> list[list[float]]:
        client = AsyncOpenAI(api_key=self._require_api_key(), timeout=self._timeout)
        last_error: RateLimitError | None = None

        for attempt in range(_MAX_ATTEMPTS):
            try:
                started = perf_counter()
                response = await client.embeddings.create(
                    model=self._model,
                    input=texts,
                )
                latency_ms = (perf_counter() - started) * 1000
                logger.info(
                    "embedding_batch_completed",
                    extra={
                        "batch_index": batch_index,
                        "batch_size": len(texts),
                        "batch_tokens": batch_tokens,
                        "latency_ms": round(latency_ms, 2),
                    },
                )
                vectors = [item.embedding for item in response.data]
                return self._validate_vectors(vectors)
            except RateLimitError as exc:
                last_error = exc
                if attempt == _MAX_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(_BACKOFF_SECONDS[attempt])

        if last_error is not None:
            raise last_error
        raise RuntimeError("embedding batch failed without a captured error")

    async def embed_one(self, text: str) -> list[float]:
        vectors = await self._embed_batch(
            [text],
            batch_index=0,
            batch_tokens=0,
        )
        return vectors[0]

    async def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        if not chunks:
            self.last_total_tokens = 0
            self.last_cost_usd = 0.0
            return []

        embedded: list[EmbeddedChunk] = []
        total_tokens = 0

        for batch_index, start in enumerate(range(0, len(chunks), self._batch_size)):
            batch = chunks[start : start + self._batch_size]
            batch_tokens = sum(chunk.token_count for chunk in batch)
            total_tokens += batch_tokens
            texts = [chunk.text for chunk in batch]
            vectors = await self._embed_batch(
                texts,
                batch_index=batch_index,
                batch_tokens=batch_tokens,
            )
            for chunk, vector in zip(batch, vectors, strict=True):
                embedded.append(
                    EmbeddedChunk(
                        chunk_id=chunk.chunk_id,
                        text=chunk.text,
                        metadata=chunk.metadata,
                        token_count=chunk.token_count,
                        embedding=vector,
                    )
                )

        self.last_total_tokens = total_tokens
        self.last_cost_usd = total_tokens / 1_000_000 * COST_PER_MILLION_TOKENS
        return embedded
