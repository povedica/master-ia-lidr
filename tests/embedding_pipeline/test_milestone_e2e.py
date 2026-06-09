"""Milestone end-to-end tests for Session 07 embedding pipeline (feature-035)."""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.embedding_pipeline.schemas import Chunk, EmbeddedChunk
from app.main import app
from app.routers import embeddings
from app.scripts.compare import main as compare_main

EMBEDDING_DIM = 1536
INGEST_PATH = "/api/v1/embeddings/ingest"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_budgets.json"

REQUIRED_METADATA_KEYS = {
    "budget_id",
    "component_id",
    "client_sector",
    "main_technology",
    "year",
    "complexity",
    "estimated_hours",
}

LINEAGE_METADATA_KEYS = {"source_name", "source_version", "location"}
CHUNK_ID_PATTERN = re.compile(r"^.+::.+$")


def _load_sample_budgets_payload() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


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


@pytest.fixture
def milestone_client() -> TestClient:
    fake_embedder = _FakeEmbedder()
    app.dependency_overrides[embeddings.get_embedder] = lambda: fake_embedder  # type: ignore[return-value]
    try:
        with TestClient(app) as test_client:
            test_client.fake_embedder = fake_embedder  # type: ignore[attr-defined]
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_e2e_01_ingest_returns_200(milestone_client: TestClient) -> None:
    response = milestone_client.post(INGEST_PATH, json=_load_sample_budgets_payload())
    assert response.status_code == 200


def test_e2e_02_chunk_count_matches_components(milestone_client: TestClient) -> None:
    payload = _load_sample_budgets_payload()
    expected = sum(len(b["components"]) for b in payload["budgets"])  # type: ignore[index]
    response = milestone_client.post(INGEST_PATH, json=payload)
    assert len(response.json()["chunks"]) == expected == 3


def test_e2e_03_stats_from_embedder(milestone_client: TestClient) -> None:
    response = milestone_client.post(INGEST_PATH, json=_load_sample_budgets_payload())
    stats = response.json()["stats"]
    fake: _FakeEmbedder = milestone_client.fake_embedder  # type: ignore[attr-defined]
    assert stats["total_budgets"] == 3
    assert stats["total_chunks"] == 3
    assert stats["total_tokens"] == fake.last_total_tokens
    assert stats["estimated_cost_usd"] == pytest.approx(fake.last_cost_usd)


def test_e2e_04_chunk_ids_and_metadata(milestone_client: TestClient) -> None:
    response = milestone_client.post(INGEST_PATH, json=_load_sample_budgets_payload())
    for chunk in response.json()["chunks"]:
        assert CHUNK_ID_PATTERN.match(chunk["chunk_id"])
        metadata = chunk["metadata"]
        assert REQUIRED_METADATA_KEYS.issubset(metadata.keys())
        assert LINEAGE_METADATA_KEYS.issubset(metadata.keys())
        assert metadata["source_name"] == "inline"
        assert metadata["source_version"] == "api"


def test_e2e_05_embeddings_dimension_and_order(milestone_client: TestClient) -> None:
    response = milestone_client.post(INGEST_PATH, json=_load_sample_budgets_payload())
    chunks = response.json()["chunks"]
    assert [c["chunk_id"] for c in chunks] == [
        "BUD-2024-014::AUTH-001",
        "BUD-2024-099::PAY-001",
        "BUD-2024-099::PAY-002",
    ]
    for chunk in chunks:
        assert len(chunk["embedding"]) == EMBEDDING_DIM
        assert all(math.isfinite(x) for x in chunk["embedding"])


def test_e2e_06_stats_not_recomputed_from_chunk_tokens(milestone_client: TestClient) -> None:
    fake: _FakeEmbedder = milestone_client.fake_embedder  # type: ignore[attr-defined]
    fake.last_total_tokens = 999
    fake.last_cost_usd = 0.42
    response = milestone_client.post(INGEST_PATH, json=_load_sample_budgets_payload())
    stats = response.json()["stats"]
    assert stats["total_tokens"] == 999
    assert stats["estimated_cost_usd"] == pytest.approx(0.42)


def test_e2e_07_empty_and_zero_component_budgets(milestone_client: TestClient) -> None:
    empty_response = milestone_client.post(INGEST_PATH, json={"budgets": []})
    assert empty_response.status_code == 200
    assert empty_response.json()["chunks"] == []

    payload = _load_sample_budgets_payload()
    zero_only = {
        "budgets": [b for b in payload["budgets"] if b["budget_id"] == "BUD-2024-000"]
    }
    zero_response = milestone_client.post(INGEST_PATH, json=zero_only)
    assert zero_response.status_code == 200
    assert zero_response.json()["chunks"] == []
    assert zero_response.json()["stats"]["total_budgets"] == 1
    assert zero_response.json()["stats"]["total_chunks"] == 0


def test_e2e_08_uses_real_chunker_with_fake_embedder_only(
    milestone_client: TestClient,
) -> None:
    app.dependency_overrides.pop(embeddings.get_chunker, None)
    response = milestone_client.post(INGEST_PATH, json=_load_sample_budgets_payload())
    assert response.status_code == 200
    first_text = response.json()["chunks"][0]["text"]
    assert first_text.startswith("## Project context")


@pytest.mark.slow
def test_smoke_01_real_key_ingest_of_fixture() -> None:
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        pytest.skip("OPENAI_API_KEY not set")

    with TestClient(app) as client:
        response = client.post(INGEST_PATH, json=_load_sample_budgets_payload())

    assert response.status_code == 200
    body = response.json()
    assert len(body["chunks"]) == 3
    assert all(len(c["embedding"]) == EMBEDDING_DIM for c in body["chunks"])


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
