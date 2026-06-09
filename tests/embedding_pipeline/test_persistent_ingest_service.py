"""Service tests for persisted embedding ingest (feature-037)."""

from __future__ import annotations

import math
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.errors import DuplicateDocumentError
from app.embedding_pipeline.persistent_ingest import run_persistent_ingest
from app.embedding_pipeline.schemas import (
    Budget,
    Chunk,
    EmbeddedChunk,
    PersistentIngestRequest,
)
from tests.embedding_pipeline.conftest import SAMPLE_BUDGET
from tests.embedding_pipeline.test_chunker import SECOND_BUDGET

EMBEDDING_DIM = 1536
SOURCE_PATH = "data/budgets/budget_2024_q1_fintech.json"


def _make_vector(seed: float = 0.1) -> list[float]:
    return [seed + i * 0.0001 for i in range(EMBEDDING_DIM)]


def _request(
    *,
    source_path: str = SOURCE_PATH,
    content: dict[str, object] | None = None,
) -> PersistentIngestRequest:
    return PersistentIngestRequest(
        source_path=source_path,
        document_type="historical_budget",
        content=Budget.model_validate(content or SAMPLE_BUDGET),
    )


class _FakeEmbedder:
    def __init__(self) -> None:
        self.call_count = 0

    async def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        self.call_count += 1
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


class _FailingEmbedder:
    async def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        del chunks
        raise RuntimeError("embedding provider unavailable")


class _FakeSession:
    """Minimal async session stand-in for service tests."""

    def __init__(self, repository: "_InMemoryRepository") -> None:
        self._repository = repository
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self._repository.finalize_pending()
        self.committed = True

    async def rollback(self) -> None:
        self._repository.discard_pending()
        self.rolled_back = True


class _InMemoryRepository:
    def __init__(self, *, fail_on_insert_chunks: bool = False) -> None:
        self._next_id = 1
        self.source_paths: dict[str, int] = {}
        self.chunks_by_document: dict[int, list[dict[str, Any]]] = {}
        self.fail_on_insert_chunks = fail_on_insert_chunks
        self._pending_document: tuple[str, int, str, dict[str, object]] | None = None
        self._pending_chunks: list[dict[str, Any]] | None = None

    async def find_document_id_by_source_path(
        self,
        session: AsyncSession,
        source_path: str,
    ) -> int | None:
        del session
        return self.source_paths.get(source_path)

    async def insert_document(
        self,
        session: AsyncSession,
        *,
        source_path: str,
        document_type: str,
        metadata: dict[str, object],
    ) -> int:
        del session
        document_id = self._next_id
        self._pending_document = (source_path, document_id, document_type, metadata)
        return document_id

    async def insert_chunks(
        self,
        session: AsyncSession,
        *,
        document_id: int,
        embedded_chunks: list[EmbeddedChunk],
    ) -> int:
        del session
        if self.fail_on_insert_chunks:
            raise RuntimeError("chunk insert failed")
        rows = [
            {
                "chunk_type": "budget_component",
                "content": embedded.text,
                "metadata": embedded.metadata,
                "embedding": embedded.embedding,
            }
            for embedded in embedded_chunks
        ]
        self._pending_chunks = rows
        return len(rows)

    def finalize_pending(self) -> None:
        if self._pending_document is None:
            return
        source_path, document_id, _document_type, _metadata = self._pending_document
        self.source_paths[source_path] = document_id
        self.chunks_by_document[document_id] = list(self._pending_chunks or [])
        self._next_id = document_id + 1
        self._pending_document = None
        self._pending_chunks = None

    def discard_pending(self) -> None:
        self._pending_document = None
        self._pending_chunks = None


def _session_for(repository: _InMemoryRepository) -> _FakeSession:
    return _FakeSession(repository)


@pytest.mark.asyncio
async def test_run_persistent_ingest_persists_document_and_chunks() -> None:
    repository = _InMemoryRepository()
    embedder = _FakeEmbedder()
    session = _session_for(repository)
    chunker = JSONStructuralChunker(embedding_model="text-embedding-3-small")
    request = _request()

    response = await run_persistent_ingest(
        request,
        session=session,  # type: ignore[arg-type]
        chunker=chunker,
        embedder=embedder,
        repository=repository,  # type: ignore[arg-type]
    )

    assert response.document_id == 1
    assert response.chunks_created == 1
    assert response.embedding_dimension == EMBEDDING_DIM
    assert response.ingestion_time_ms >= 0
    assert repository.source_paths[SOURCE_PATH] == 1
    assert len(repository.chunks_by_document[1]) == 1
    assert embedder.call_count == 1


@pytest.mark.asyncio
async def test_run_persistent_ingest_duplicate_raises_without_embedder_call() -> None:
    repository = _InMemoryRepository()
    repository.source_paths[SOURCE_PATH] = 42
    embedder = _FakeEmbedder()
    session = _session_for(repository)
    chunker = JSONStructuralChunker(embedding_model="text-embedding-3-small")

    with pytest.raises(DuplicateDocumentError) as exc_info:
        await run_persistent_ingest(
            _request(),
            session=session,  # type: ignore[arg-type]
            chunker=chunker,
            embedder=embedder,
            repository=repository,  # type: ignore[arg-type]
        )

    assert exc_info.value.document_id == 42
    assert embedder.call_count == 0


@pytest.mark.asyncio
async def test_run_persistent_ingest_zero_components_skips_embedder() -> None:
    zero_budget = {**SAMPLE_BUDGET, "components": []}
    repository = _InMemoryRepository()
    embedder = _FakeEmbedder()
    session = _session_for(repository)
    chunker = JSONStructuralChunker(embedding_model="text-embedding-3-small")

    response = await run_persistent_ingest(
        _request(content=zero_budget),
        session=session,  # type: ignore[arg-type]
        chunker=chunker,
        embedder=embedder,
        repository=repository,  # type: ignore[arg-type]
    )

    assert response.chunks_created == 0
    assert embedder.call_count == 0
    assert len(repository.chunks_by_document[response.document_id]) == 0


@pytest.mark.asyncio
async def test_run_persistent_ingest_embedder_failure_does_not_persist() -> None:
    repository = _InMemoryRepository()
    session = _session_for(repository)
    chunker = JSONStructuralChunker(embedding_model="text-embedding-3-small")
    request = _request(
        content={
            **SAMPLE_BUDGET,
            "components": [
                *SAMPLE_BUDGET["components"],
                SECOND_BUDGET["components"][0],
            ],
        }
    )

    with pytest.raises(RuntimeError, match="embedding provider unavailable"):
        await run_persistent_ingest(
            request,
            session=session,  # type: ignore[arg-type]
            chunker=chunker,
            embedder=_FailingEmbedder(),
            repository=repository,  # type: ignore[arg-type]
        )

    assert repository.source_paths == {}
    assert repository.chunks_by_document == {}


@pytest.mark.asyncio
async def test_run_persistent_ingest_chunk_insert_failure_does_not_persist() -> None:
    repository = _InMemoryRepository(fail_on_insert_chunks=True)
    session = _session_for(repository)
    chunker = JSONStructuralChunker(embedding_model="text-embedding-3-small")

    with pytest.raises(RuntimeError, match="chunk insert failed"):
        await run_persistent_ingest(
            _request(),
            session=session,  # type: ignore[arg-type]
            chunker=chunker,
            embedder=_FakeEmbedder(),
            repository=repository,  # type: ignore[arg-type]
        )

    assert repository.source_paths == {}
    assert repository.chunks_by_document == {}


@pytest.mark.asyncio
async def test_run_persistent_ingest_stored_embeddings_are_finite() -> None:
    repository = _InMemoryRepository()
    session = _session_for(repository)
    chunker = JSONStructuralChunker(embedding_model="text-embedding-3-small")

    await run_persistent_ingest(
        _request(),
        session=session,  # type: ignore[arg-type]
        chunker=chunker,
        embedder=_FakeEmbedder(),
        repository=repository,  # type: ignore[arg-type]
    )

    stored = repository.chunks_by_document[1][0]
    assert stored["chunk_type"] == "budget_component"
    assert len(stored["embedding"]) == EMBEDDING_DIM
    assert all(math.isfinite(x) for x in stored["embedding"])
