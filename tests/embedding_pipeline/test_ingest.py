"""Tests for shared ingest orchestration (feature-035)."""

from __future__ import annotations

import math

import pytest

from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.ingest import run_ingest
from app.embedding_pipeline.schemas import Budget, Chunk, EmbeddedChunk
from tests.embedding_pipeline.conftest import SAMPLE_BUDGET
from tests.embedding_pipeline.test_chunker import SECOND_BUDGET

EMBEDDING_DIM = 1536


def _make_vector(seed: float = 0.1) -> list[float]:
    return [seed + i * 0.0001 for i in range(EMBEDDING_DIM)]


class _FakeEmbedder:
    def __init__(self) -> None:
        self.last_total_tokens = 200
        self.last_cost_usd = 0.000004

    async def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        embedded: list[EmbeddedChunk] = []
        for index, chunk in enumerate(chunks):
            embedded.append(
                EmbeddedChunk(
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    metadata=chunk.metadata,
                    token_count=chunk.token_count,
                    embedding=_make_vector(0.1 + index * 0.01),
                )
            )
        return embedded


@pytest.mark.asyncio
async def test_run_ingest_returns_embedded_chunks_and_stats() -> None:
    chunker = JSONStructuralChunker(embedding_model="text-embedding-3-small")
    embedder = _FakeEmbedder()
    budgets = [
        Budget.model_validate(SAMPLE_BUDGET),
        Budget.model_validate(SECOND_BUDGET),
    ]

    response = await run_ingest(budgets, chunker, embedder)

    assert len(response.chunks) == 3
    assert response.stats.total_budgets == 2
    assert response.stats.total_chunks == 3
    assert response.stats.total_tokens == embedder.last_total_tokens
    assert response.stats.estimated_cost_usd == embedder.last_cost_usd
    for chunk in response.chunks:
        assert len(chunk.embedding) == EMBEDDING_DIM
        assert all(math.isfinite(x) for x in chunk.embedding)
