"""Milestone end-to-end tests for Session 07 embedding pipeline (feature-035/037)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.embedding_pipeline.schemas import Chunk, EmbeddedChunk
from app.main import app
from app.routers import embeddings
from app.scripts.compare import main as compare_main

EMBEDDING_DIM = 1536
INGEST_PATH = "/api/v1/embeddings/ingest"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_budgets.json"


def _load_sample_budgets() -> list[dict[str, object]]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return list(payload["budgets"])  # type: ignore[index]


def _persisted_payload(
    budget: dict[str, object],
    *,
    source_path: str | None = None,
) -> dict[str, object]:
    budget_id = str(budget["budget_id"])
    return {
        "source_path": source_path or f"data/budgets/{budget_id.lower()}.json",
        "document_type": "historical_budget",
        "content": budget,
    }


def _make_vector(seed: float = 0.1) -> list[float]:
    return [seed + i * 0.0001 for i in range(EMBEDDING_DIM)]


class _FakeEmbedder:
    def __init__(self, *, last_total_tokens: int = 321, last_cost_usd: float = 0.000006) -> None:
        self.last_total_tokens = last_total_tokens
        self.last_cost_usd = last_cost_usd

    async def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
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
        del session
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
def milestone_client() -> TestClient:
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


def _post_all_fixture_budgets(client: TestClient) -> list[dict[str, object]]:
    responses: list[dict[str, object]] = []
    for budget in _load_sample_budgets():
        response = client.post(INGEST_PATH, json=_persisted_payload(budget))
        assert response.status_code == 200
        responses.append(response.json())
    return responses


def test_e2e_01_ingest_returns_200(milestone_client: TestClient) -> None:
    budget = _load_sample_budgets()[0]
    response = milestone_client.post(INGEST_PATH, json=_persisted_payload(budget))
    assert response.status_code == 200


def test_e2e_02_chunk_count_matches_components(milestone_client: TestClient) -> None:
    responses = _post_all_fixture_budgets(milestone_client)
    expected = sum(len(b["components"]) for b in _load_sample_budgets())  # type: ignore[index]
    assert sum(int(r["chunks_created"]) for r in responses) == expected == 3


def test_e2e_03_persisted_response_shape(milestone_client: TestClient) -> None:
    budget = _load_sample_budgets()[0]
    response = milestone_client.post(INGEST_PATH, json=_persisted_payload(budget))
    body = response.json()
    assert set(body.keys()) == {
        "document_id",
        "chunks_created",
        "embedding_dimension",
        "ingestion_time_ms",
    }
    assert body["embedding_dimension"] == EMBEDDING_DIM


def test_e2e_04_chunk_metadata_persisted_in_repository(milestone_client: TestClient) -> None:
    budget = _load_sample_budgets()[0]
    response = milestone_client.post(INGEST_PATH, json=_persisted_payload(budget))
    document_id = int(response.json()["document_id"])
    repository: _InMemoryRepository = milestone_client.repository  # type: ignore[attr-defined]
    stored = repository.chunks_by_document[document_id][0]
    metadata = stored["metadata"]
    assert metadata["budget_id"] == "BUD-2024-014"
    assert metadata["component_id"] == "AUTH-001"
    assert metadata["source_name"] == "inline"
    assert metadata["source_version"] == "api"


def test_e2e_05_embeddings_dimension_persisted(milestone_client: TestClient) -> None:
    _post_all_fixture_budgets(milestone_client)
    repository: _InMemoryRepository = milestone_client.repository  # type: ignore[attr-defined]
    for rows in repository.chunks_by_document.values():
        for row in rows:
            assert len(row["embedding"]) == EMBEDDING_DIM


def test_e2e_06_duplicate_source_path_returns_409(milestone_client: TestClient) -> None:
    budget = _load_sample_budgets()[0]
    payload = _persisted_payload(budget)
    first = milestone_client.post(INGEST_PATH, json=payload)
    duplicate = milestone_client.post(INGEST_PATH, json=payload)
    assert first.status_code == 200
    assert duplicate.status_code == 409
    assert duplicate.json()["document_id"] == first.json()["document_id"]


def test_e2e_07_zero_component_budget_persists_document_only(
    milestone_client: TestClient,
) -> None:
    zero_budget = next(b for b in _load_sample_budgets() if b["budget_id"] == "BUD-2024-000")
    response = milestone_client.post(INGEST_PATH, json=_persisted_payload(zero_budget))
    assert response.status_code == 200
    body = response.json()
    assert body["chunks_created"] == 0
    repository: _InMemoryRepository = milestone_client.repository  # type: ignore[attr-defined]
    assert len(repository.chunks_by_document[int(body["document_id"])]) == 0


def test_e2e_08_uses_real_chunker_with_fake_embedder_only(
    milestone_client: TestClient,
) -> None:
    app.dependency_overrides.pop(embeddings.get_chunker, None)
    budget = _load_sample_budgets()[0]
    response = milestone_client.post(INGEST_PATH, json=_persisted_payload(budget))
    assert response.status_code == 200
    repository: _InMemoryRepository = milestone_client.repository  # type: ignore[attr-defined]
    document_id = int(response.json()["document_id"])
    first_text = repository.chunks_by_document[document_id][0]["content"]
    assert first_text.startswith("## Project context")


@pytest.mark.slow
def test_smoke_01_real_key_ingest_of_fixture() -> None:
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        pytest.skip("OPENAI_API_KEY not set")
    if not os.environ.get("DATABASE_URL", "").strip():
        pytest.skip("DATABASE_URL not set")

    with TestClient(app) as client:
        budget = _load_sample_budgets()[0]
        response = client.post(INGEST_PATH, json=_persisted_payload(budget))

    assert response.status_code == 200
    body = response.json()
    assert body["chunks_created"] == 1
    assert body["embedding_dimension"] == EMBEDDING_DIM


@pytest.mark.slow
def test_smoke_02_compare_cli_exit_zero() -> None:
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        pytest.skip("OPENAI_API_KEY not set")

    exit_code = compare_main(
        [
            "--text-a",
            "OAuth authentication backend",
            "--text-b",
            "JWT authorization service",
        ]
    )
    assert exit_code == 0
