"""Integration tests for POST /api/v1/embeddings/ingest (feature-033)."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.embedding_pipeline.schemas import Chunk, EmbeddedChunk
from app.main import app
from app.routers import embeddings
from tests.embedding_pipeline.conftest import SAMPLE_BUDGET
from tests.embedding_pipeline.test_chunker import SECOND_BUDGET

EMBEDDING_DIM = 1536
INGEST_PATH = "/api/v1/embeddings/ingest"


def _make_vector(seed: float = 0.1) -> list[float]:
    return [seed + i * 0.0001 for i in range(EMBEDDING_DIM)]


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


def _two_budget_payload() -> dict[str, object]:
    return {"budgets": [SAMPLE_BUDGET, SECOND_BUDGET]}


@pytest.fixture
def client() -> TestClient:
    fake_embedder = _FakeEmbedder(last_total_tokens=200, last_cost_usd=0.000004)
    app.dependency_overrides[embeddings.get_embedder] = lambda: fake_embedder  # type: ignore[return-value]
    try:
        with TestClient(app) as test_client:
            test_client.fake_embedder = fake_embedder  # type: ignore[attr-defined]
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_openapi_lists_ingest_route() -> None:
    schema = app.openapi()
    assert INGEST_PATH in schema["paths"]
    assert "post" in schema["paths"][INGEST_PATH]


def test_ingest_returns_populated_response(client: TestClient) -> None:
    response = client.post(INGEST_PATH, json=_two_budget_payload())
    assert response.status_code == 200
    body = response.json()
    assert len(body["chunks"]) == 3
    assert body["stats"]["total_budgets"] == 2
    assert body["stats"]["total_chunks"] == 3
    assert body["stats"]["total_tokens"] == 200
    assert body["stats"]["estimated_cost_usd"] == pytest.approx(0.000004)
    for chunk in body["chunks"]:
        assert len(chunk["embedding"]) == EMBEDDING_DIM
        assert all(math.isfinite(x) for x in chunk["embedding"])


def test_ingest_chunk_count_matches_components(client: TestClient) -> None:
    response = client.post(INGEST_PATH, json=_two_budget_payload())
    assert response.status_code == 200
    payload = _two_budget_payload()
    expected_components = sum(len(b["components"]) for b in payload["budgets"])  # type: ignore[index]
    assert len(response.json()["chunks"]) == expected_components


def test_ingest_malformed_body_returns_422(client: TestClient) -> None:
    response = client.post(INGEST_PATH, json={"not_budgets": []})
    assert response.status_code == 422


def test_ingest_empty_budgets_returns_zeroed_stats_without_embed_call(
    client: TestClient,
) -> None:
    response = client.post(INGEST_PATH, json={"budgets": []})
    assert response.status_code == 200
    body = response.json()
    assert body["chunks"] == []
    assert body["stats"] == {
        "total_budgets": 0,
        "total_chunks": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
    }
    assert client.fake_embedder.embed_many_called is True  # type: ignore[attr-defined]


def test_ingest_embedder_failure_returns_safe_500_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app.dependency_overrides[embeddings.get_embedder] = lambda: _FailingEmbedder()  # type: ignore[return-value]
    try:
        with TestClient(app) as test_client:
            with caplog.at_level("ERROR"):
                response = test_client.post(INGEST_PATH, json=_two_budget_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to embed budgets."
    assert "OpenAI API key" not in response.text
    assert any(
        record.message == "embedding_ingest_failed"
        and getattr(record, "request_id", "").startswith("emb_")
        and getattr(record, "error_type", "") == "RuntimeError"
        for record in caplog.records
    )


def test_root_lists_embeddings_endpoint() -> None:
    with TestClient(app) as test_client:
        response = test_client.get("/")
    assert response.status_code == 200
    assert response.json().get("embeddings") == "POST /api/v1/embeddings/ingest"
