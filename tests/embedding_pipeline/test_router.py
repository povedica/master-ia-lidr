"""Integration tests for POST /api/v1/embeddings/ingest (feature-037)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.embedding_pipeline.schemas import Chunk, EmbeddedChunk
from app.main import app
from app.routers import embeddings
from tests.embedding_pipeline.conftest import SAMPLE_BUDGET

EMBEDDING_DIM = 1536
INGEST_PATH = "/api/v1/embeddings/ingest"
SOURCE_PATH = "data/budgets/budget_2024_q1_fintech.json"


def _make_vector(seed: float = 0.1) -> list[float]:
    return [seed + i * 0.0001 for i in range(EMBEDDING_DIM)]


def _persisted_payload(
    *,
    source_path: str = SOURCE_PATH,
    content: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "source_path": source_path,
        "document_type": "historical_budget",
        "content": content or SAMPLE_BUDGET,
    }


class _FakeEmbedder:
    def __init__(
        self,
        *,
        last_total_tokens: int = 150,
        last_cost_usd: float = 0.000003,
    ) -> None:
        self.last_total_tokens = last_total_tokens
        self.last_cost_usd = last_cost_usd
        self.embed_many_called = False

    async def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        self.embed_many_called = True
        if not chunks:
            self.last_total_tokens = 0
            self.last_cost_usd = 0.0
            return []
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


class _FailingEmbedder:
    last_total_tokens = 0
    last_cost_usd = 0.0

    async def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        del chunks
        raise RuntimeError("OpenAI API key is not configured.")


class _FakeSession:
    def __init__(self, repository: "_InMemoryRepository") -> None:
        self._repository = repository

    async def commit(self) -> None:
        self._repository.finalize_pending()

    async def rollback(self) -> None:
        self._repository.discard_pending()


class _InMemoryRepository:
    def __init__(self) -> None:
        self._next_id = 1
        self.source_paths: dict[str, int] = {}
        self.chunks_by_document: dict[int, list[dict[str, Any]]] = {}
        self._pending_document: tuple[str, int, str, dict[str, object]] | None = None
        self._pending_chunks: list[dict[str, Any]] | None = None

    async def find_document_id_by_source_path(self, session: object, source_path: str) -> int | None:
        del session
        return self.source_paths.get(source_path)

    async def insert_document(
        self,
        session: object,
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
        session: object,
        *,
        document_id: int,
        embedded_chunks: list[EmbeddedChunk],
    ) -> int:
        del session, document_id
        self._pending_chunks = [
            {
                "content": embedded.text,
                "metadata": embedded.metadata,
                "embedding": embedded.embedding,
            }
            for embedded in embedded_chunks
        ]
        return len(embedded_chunks)

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


@pytest.fixture
def persisted_client() -> TestClient:
    repository = _InMemoryRepository()
    fake_embedder = _FakeEmbedder()
    fake_session = _FakeSession(repository)

    async def _session_override():
        yield fake_session

    app.dependency_overrides[embeddings.get_db_session] = _session_override
    app.dependency_overrides[embeddings.get_ingest_repository] = lambda: repository  # type: ignore[assignment]
    app.dependency_overrides[embeddings.get_embedder] = lambda: fake_embedder  # type: ignore[return-value]
    try:
        with TestClient(app) as test_client:
            test_client.fake_embedder = fake_embedder  # type: ignore[attr-defined]
            test_client.repository = repository  # type: ignore[attr-defined]
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_openapi_lists_ingest_route() -> None:
    schema = app.openapi()
    assert INGEST_PATH in schema["paths"]
    assert "post" in schema["paths"][INGEST_PATH]


def test_ingest_returns_persisted_metadata_without_vectors(
    persisted_client: TestClient,
) -> None:
    response = persisted_client.post(INGEST_PATH, json=_persisted_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == 1
    assert body["chunks_created"] == 1
    assert body["embedding_dimension"] == EMBEDDING_DIM
    assert "ingestion_time_ms" in body
    assert "chunks" not in body
    assert "stats" not in body


def test_ingest_chunk_count_matches_components(persisted_client: TestClient) -> None:
    response = persisted_client.post(INGEST_PATH, json=_persisted_payload())
    assert response.status_code == 200
    assert response.json()["chunks_created"] == len(SAMPLE_BUDGET["components"])


def test_ingest_malformed_body_returns_422(persisted_client: TestClient) -> None:
    response = persisted_client.post(INGEST_PATH, json={"source_path": SOURCE_PATH})
    assert response.status_code == 422


def test_ingest_zero_components_skips_embedder(persisted_client: TestClient) -> None:
    zero_budget = {**SAMPLE_BUDGET, "components": []}
    response = persisted_client.post(
        INGEST_PATH,
        json=_persisted_payload(content=zero_budget),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["chunks_created"] == 0
    assert persisted_client.fake_embedder.embed_many_called is False  # type: ignore[attr-defined]


def test_ingest_duplicate_returns_409_without_embedder_call(
    persisted_client: TestClient,
) -> None:
    first = persisted_client.post(INGEST_PATH, json=_persisted_payload())
    assert first.status_code == 200
    persisted_client.fake_embedder.embed_many_called = False  # type: ignore[attr-defined]

    duplicate = persisted_client.post(INGEST_PATH, json=_persisted_payload())
    assert duplicate.status_code == 409
    body = duplicate.json()
    assert body["detail"] == "Document already ingested"
    assert body["document_id"] == first.json()["document_id"]
    assert persisted_client.fake_embedder.embed_many_called is False  # type: ignore[attr-defined]


def test_ingest_embedder_failure_returns_safe_500_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = _InMemoryRepository()
    fake_session = _FakeSession(repository)
    async def _session_override():
        yield fake_session

    app.dependency_overrides[embeddings.get_db_session] = _session_override
    app.dependency_overrides[embeddings.get_ingest_repository] = lambda: repository  # type: ignore[assignment]
    app.dependency_overrides[embeddings.get_embedder] = lambda: _FailingEmbedder()  # type: ignore[return-value]
    try:
        with TestClient(app) as test_client:
            with caplog.at_level("ERROR"):
                response = test_client.post(INGEST_PATH, json=_persisted_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to ingest budget document."
    assert "OpenAI API key" not in response.text
    assert repository.source_paths == {}
    assert any(
        record.message == "embedding_ingest_failed"
        and getattr(record, "source_path", "") == SOURCE_PATH
        and getattr(record, "error_type", "") == "RuntimeError"
        for record in caplog.records
    )


def test_root_lists_embeddings_endpoint() -> None:
    with TestClient(app) as test_client:
        response = test_client.get("/")
    assert response.status_code == 200
    assert response.json().get("embeddings") == "POST /api/v1/embeddings/ingest"
