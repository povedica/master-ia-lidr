"""API tests for RAG stage endpoints (feature-062)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.estimation_query import EstimationQuery
from app.schemas.rag_estimation_result import RagEstimationResult
from app.schemas.rag_structure_result import RagStructureModule, RagStructureResult, RagStructureTask

REFORMULATE_PATH = "/api/v1/estimate/rag/stages/reformulate"
ASSEMBLE_PATH = "/api/v1/estimate/rag/stages/assemble"
VERIFY_PATH = "/api/v1/estimate/rag/stages/verify"
STRUCTURE_PATH = "/api/v1/estimate/rag/stages/structure"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_reformulate_stage_returns_search_text(client: TestClient) -> None:
    query = EstimationQuery(
        question="CRM integration",
        search_facets=["crm", "integration"],
        component_hints=[],
        sector_filters=[],
    )
    with patch(
        "app.routers.rag_stages.reformulate_query",
        new_callable=AsyncMock,
        return_value=query,
    ):
        response = client.post(
            REFORMULATE_PATH,
            json={"question": "How long for CRM integration?"},
        )
    assert response.status_code == 200
    body = response.json()
    assert "search_text" in body
    assert body["query"]["question"] == "CRM integration"


def test_assemble_stage_truncates_chunks(client: TestClient) -> None:
    chunk = {
        "chunk_id": 1,
        "document_id": 10,
        "content": "Short chunk content for assemble stage.",
        "collection": "budgets",
        "budget_id": "BUD-1",
        "metadata": {},
    }
    response = client.post(
        ASSEMBLE_PATH,
        json={"chunks": [chunk], "max_context_tokens": 8000},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kept_chunks"]
    assert body["token_count"] > 0
    assert "[CHUNK START]" in body["context_block"]


def test_verify_stage_returns_reports_without_pipeline(client: TestClient) -> None:
    estimate = RagEstimationResult(
        summary="A grounded estimate summary with enough words for validation.",
        line_items=[],
        total_hours=0.0,
    )
    chunk = {
        "chunk_id": 5,
        "document_id": 2,
        "content": "Budget line with 40 hours backend work.",
        "collection": "budgets",
        "metadata": {"estimated_hours": 40},
    }
    with patch(
        "app.routers.rag_stages.gate_estimate",
        new_callable=AsyncMock,
    ) as gate_mock:
        from app.schemas.hallucination_report import HallucinationReport

        gate_mock.return_value = HallucinationReport(
            request_id="req",
            lines=[],
            counts={},
            has_degraded=False,
        )
        response = client.post(
            VERIFY_PATH,
            json={"estimate": estimate.model_dump(), "kept_chunks": [chunk], "use_judge": False},
        )
    assert response.status_code == 200
    body = response.json()
    assert "citation_report" in body
    assert "coherence_report" in body
    assert "hallucination_report" in body


def test_structure_stage_returns_modules(client: TestClient) -> None:
    structure = RagStructureResult(
        summary="Structure summary with enough words for validation here.",
        modules=[
            RagStructureModule(
                name="Auth",
                tasks=[RagStructureTask(name="OAuth", description="Google login")],
            )
        ],
    )
    query = EstimationQuery(
        question="Auth work",
        search_facets=["auth"],
        component_hints=[],
        sector_filters=[],
    )
    with patch(
        "app.routers.rag_stages.generate_structure",
        new_callable=AsyncMock,
        return_value=(structure, None, None),
    ):
        response = client.post(
            STRUCTURE_PATH,
            json={"query": query.model_dump()},
        )
    assert response.status_code == 200
    assert response.json()["structure"]["modules"][0]["name"] == "Auth"
