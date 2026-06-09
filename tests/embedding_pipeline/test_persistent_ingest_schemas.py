"""Tests for persisted ingest request/response schemas (feature-037)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.embedding_pipeline.schemas import Budget, PersistentIngestRequest, PersistentIngestResponse
from tests.embedding_pipeline.conftest import SAMPLE_BUDGET

SAMPLE_SOURCE_PATH = "data/budgets/budget_2024_q1_fintech.json"


def _valid_request_payload() -> dict[str, object]:
    return {
        "source_path": SAMPLE_SOURCE_PATH,
        "document_type": "historical_budget",
        "content": SAMPLE_BUDGET,
    }


def test_persistent_ingest_request_from_valid_data() -> None:
    request = PersistentIngestRequest.model_validate(_valid_request_payload())
    assert request.source_path == SAMPLE_SOURCE_PATH
    assert request.document_type == "historical_budget"
    assert isinstance(request.content, Budget)
    assert request.content.budget_id == SAMPLE_BUDGET["budget_id"]
    assert request.metadata == {}


def test_persistent_ingest_request_accepts_optional_metadata() -> None:
    payload = {**_valid_request_payload(), "metadata": {"team": "platform"}}
    request = PersistentIngestRequest.model_validate(payload)
    assert request.metadata == {"team": "platform"}


def test_persistent_ingest_request_rejects_missing_source_path() -> None:
    payload = _valid_request_payload()
    del payload["source_path"]  # type: ignore[operator]
    with pytest.raises(ValidationError):
        PersistentIngestRequest.model_validate(payload)


def test_persistent_ingest_request_rejects_invalid_content() -> None:
    payload = {**_valid_request_payload(), "content": {"budget_id": "only-id"}}
    with pytest.raises(ValidationError):
        PersistentIngestRequest.model_validate(payload)


def test_persistent_ingest_response_from_valid_data() -> None:
    response = PersistentIngestResponse(
        document_id=42,
        chunks_created=17,
        embedding_dimension=1536,
        ingestion_time_ms=1240,
    )
    assert response.document_id == 42
    assert response.chunks_created == 17
    assert response.embedding_dimension == 1536
    assert response.ingestion_time_ms == 1240
