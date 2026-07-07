"""Integration-style tests for transcript ingest and collection routing (feature-063)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.embedding_pipeline.advanced_retrieval import advanced_retrieve
from app.embedding_pipeline.collections import Collection
from app.embedding_pipeline.parsers.transcript_txt import (
    CHUNK_TYPE_MEETING_SEGMENT,
    parse_transcript_text,
)
from app.embedding_pipeline.rerank import NoOpReranker
from app.embedding_pipeline.schemas import Chunk, EmbeddedChunk, SearchResult
from app.embedding_pipeline.stage_config import StageConfig
from app.embedding_pipeline.text_corpus_ingest import run_text_corpus_ingest

EMBEDDING_DIM = 1536
FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample_transcript.txt"


def _make_vector(seed: float = 0.1) -> list[float]:
    return [seed + i * 0.0001 for i in range(EMBEDDING_DIM)]


class _FakeEmbedder:
    async def embed_one(self, text: str) -> list[float]:
        del text
        return _make_vector()

    async def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        return [
            EmbeddedChunk(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                metadata=chunk.metadata,
                token_count=chunk.token_count,
                embedding=_make_vector(0.1 + index * 0.01),
            )
            for index, chunk in enumerate(chunks)
        ]


class _TrackingRepository:
    def __init__(self) -> None:
        self._next_id = 1
        self.last_collection: str | None = None
        self.last_chunk_type: str | None = None

    async def find_document_id_by_source_path(self, session, source_path: str) -> int | None:
        del session, source_path
        return None

    async def insert_document(
        self,
        session,
        *,
        source_path: str,
        document_type: str,
        metadata: dict[str, object],
    ) -> int:
        del session, source_path, document_type, metadata
        document_id = self._next_id
        self._next_id += 1
        return document_id

    async def insert_chunks(
        self,
        session,
        *,
        document_id: int,
        embedded_chunks: list[EmbeddedChunk],
        collection: str = "budgets",
        chunk_type: str = "budget_component",
    ) -> int:
        del session, document_id
        count = len(embedded_chunks)
        self.last_collection = collection
        self.last_chunk_type = chunk_type
        return count


class _FakeSession:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _CollectionAwareVectorRepository:
    def __init__(self) -> None:
        self.budget_chunk = SearchResult(
            chunk_id=101,
            document_id=1,
            chunk_type="budget_component",
            content="Budget line item",
            distance=0.2,
            metadata={"budget_id": "BUD-2024-014"},
        )
        self.transcript_chunk = SearchResult(
            chunk_id=202,
            document_id=2,
            chunk_type=CHUNK_TYPE_MEETING_SEGMENT,
            content="Meeting transcript kick-off discussion",
            distance=0.15,
            metadata={"transcript_id": "demo-transcript"},
        )

    async def search_chunks(self, session, *, query_vector, k, filters=None):
        del session, query_vector, k
        if filters is not None and filters.collection == Collection.TRANSCRIPTS.value:
            return [self.transcript_chunk]
        if filters is not None and filters.collection == Collection.BUDGETS.value:
            return [self.budget_chunk]
        return [self.budget_chunk, self.transcript_chunk]


@pytest.mark.asyncio
async def test_run_text_corpus_ingest_persists_transcripts_collection() -> None:
    repository = _TrackingRepository()
    segments = parse_transcript_text(
        FIXTURE.read_text(encoding="utf-8"),
        source_path=str(FIXTURE),
        transcript_id="demo-transcript",
    )

    result = await run_text_corpus_ingest(
        _FakeSession(),
        source_path=str(FIXTURE),
        document_type="transcript",
        collection=Collection.TRANSCRIPTS.value,
        chunk_type=CHUNK_TYPE_MEETING_SEGMENT,
        segments=segments,
        embedder=_FakeEmbedder(),
        repository=repository,
    )

    assert result.chunks_created == len(segments)
    assert repository.last_collection == Collection.TRANSCRIPTS.value
    assert repository.last_chunk_type == CHUNK_TYPE_MEETING_SEGMENT


@pytest.mark.asyncio
async def test_advanced_retrieve_finds_transcript_chunk_when_routing_enabled() -> None:
    settings = Settings(_env_file=None, retrieval_routing_enabled=True)
    config = StageConfig(
        search_mode="vector",
        rerank=False,
        query_transform=False,
        routing_enabled=True,
        fusion="rrf",
        temporal_decay=False,
    )

    response = await advanced_retrieve(
        AsyncMock(),
        "client meeting transcript kick-off",
        config,
        recall_k=5,
        top_k_final=1,
        embedder=_FakeEmbedder(),
        reranker=NoOpReranker(),
        settings=settings,
        vector_repository=_CollectionAwareVectorRepository(),
        lexical_repository=AsyncMock(),
    )

    assert len(response.results) == 1
    assert response.results[0].chunk_id == 202
    assert response.results[0].collection == Collection.TRANSCRIPTS.value
