"""Integration tests for POST /api/v1/estimate/rag (feature-052)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db_session
from app.main import app
from app.routers import rag_estimations
from app.schemas.citation_report import CitationLineReport, CitationLineStatus, CitationReport
from app.schemas.coherence_report import CoherenceLineReport, CoherenceLineStatus, CoherenceReport
from app.schemas.hallucination_report import HallucinationLineGrade, HallucinationReport
from app.schemas.rag_estimation_result import RagEstimationLineItem, RagEstimationResult, SourceReference
from app.services.rag_estimation_service import RagEstimationOutcome
from app.services.structured_llm_client import StructuredCompletionError

RAG_PATH = "/api/v1/estimate/rag"


def _grounded_result(*, chunk_id: int = 42) -> RagEstimationResult:
    return RagEstimationResult(
        summary="Grounded estimate for OAuth integration from retrieved budget chunk.",
        line_items=[
            RagEstimationLineItem(
                component="authentication",
                hours=12.0,
                rationale="OAuth2 scope from retrieved chunk.",
                grounded=True,
                sources=[
                    SourceReference(
                        chunk_id=chunk_id,
                        document_id=7,
                        budget_id="BUD-2024-014",
                        evidence="OAuth2 login integration scope",
                    )
                ],
            )
        ],
        total_hours=12.0,
        insufficient_context=False,
    )


def _outcome(
    result: RagEstimationResult,
    *,
    status: CitationLineStatus = CitationLineStatus.GROUNDED_OK,
    invalid_chunk_ids: list[int] | None = None,
    coherence_status: CoherenceLineStatus = CoherenceLineStatus.COHERENT_OK,
) -> RagEstimationOutcome:
    report = CitationReport(
        request_id="req_test",
        lines=[
            CitationLineReport(
                index=0,
                component=result.line_items[0].component if result.line_items else "n/a",
                status=status,
                invalid_chunk_ids=invalid_chunk_ids or [],
            )
        ]
        if not result.line_items
        else [
            CitationLineReport(
                index=index,
                component=item.component,
                status=status,
                invalid_chunk_ids=invalid_chunk_ids or [],
            )
            for index, item in enumerate(result.line_items)
        ],
        counts={
            CitationLineStatus.GROUNDED_OK: 1 if status == CitationLineStatus.GROUNDED_OK else 0,
            CitationLineStatus.DANGLING_CITATION: 1 if status == CitationLineStatus.DANGLING_CITATION else 0,
            CitationLineStatus.INSUFFICIENT_DATA: 1 if status == CitationLineStatus.INSUFFICIENT_DATA else 0,
            CitationLineStatus.INTEGRITY_VIOLATION: 0,
        },
        has_dangling=status == CitationLineStatus.DANGLING_CITATION,
        has_integrity_violation=False,
    )
    coherence_lines = (
        []
        if not result.line_items
        else [
            CoherenceLineReport(
                index=index,
                component=item.component,
                status=coherence_status,
            )
            for index, item in enumerate(result.line_items)
        ]
    )
    coherence_counts = {s: 0 for s in CoherenceLineStatus}
    if coherence_lines:
        coherence_counts[coherence_status] = len(coherence_lines)
    coherence_report = CoherenceReport(
        request_id="req_test",
        lines=coherence_lines,
        counts=coherence_counts,
        has_violations=coherence_status != CoherenceLineStatus.COHERENT_OK,
    )
    hallucination_report = HallucinationReport(
        request_id="req_test",
        lines=[],
        counts={grade: 0 for grade in HallucinationLineGrade},
        has_degraded=False,
    )
    return RagEstimationOutcome(
        result=result,
        report=report,
        coherence_report=coherence_report,
        hallucination_report=hallucination_report,
        chunk_texts=["OAuth2 login integration scope"],
        model="gpt-4o-mini",
        provider="openai",
        usage=None,
        finish_reason="stop",
        prompt_version="estimation/rag/v1",
    )


class _FakeRagService:
    def __init__(self, outcome: RagEstimationOutcome | None = None, *, error: Exception | None = None) -> None:
        self._outcome = outcome
        self._error = error

    async def estimate(self, question: str, **kwargs) -> RagEstimationOutcome:
        del question, kwargs
        if self._error is not None:
            raise self._error
        assert self._outcome is not None
        return self._outcome


class _FakeSession:
    async def close(self) -> None:
        return None


@pytest.fixture
def rag_client() -> TestClient:
    fake_session = _FakeSession()

    async def _session_override():
        yield fake_session

    app.dependency_overrides[get_db_session] = _session_override
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_openapi_lists_rag_estimate_route() -> None:
    schema = app.openapi()
    assert RAG_PATH in schema["paths"]


def test_rag_estimate_happy_path(rag_client: TestClient) -> None:
    app.dependency_overrides[rag_estimations.get_rag_estimation_service] = lambda: _FakeRagService(  # type: ignore[return-value]
        _outcome(_grounded_result())
    )

    response = rag_client.post(RAG_PATH, json={"question": "OAuth e-commerce platform"})

    assert response.status_code == 200
    body = response.json()
    assert body["result"]["schema_version"] == "rag-1"
    assert body["citation_summary"]["dangling"] == 0
    assert body["citation_summary"]["has_dangling"] is False
    assert body["coherence_summary"]["has_violations"] is False
    assert body["coherence_summary"]["coherent_ok"] == 1
    assert body["hallucination_summary"]["has_degraded"] is False
    assert body["hallucination_summary"]["grounded"] == 0
    assert body["result"]["line_items"][0]["grounded"] is True


def test_rag_estimate_reports_dangling_citations(rag_client: TestClient) -> None:
    app.dependency_overrides[rag_estimations.get_rag_estimation_service] = lambda: _FakeRagService(  # type: ignore[return-value]
        _outcome(
            _grounded_result(chunk_id=999),
            status=CitationLineStatus.DANGLING_CITATION,
            invalid_chunk_ids=[999],
        )
    )

    response = rag_client.post(RAG_PATH, json={"question": "OAuth e-commerce platform"})

    assert response.status_code == 200
    body = response.json()
    assert body["citation_summary"]["has_dangling"] is True
    assert body["citation_summary"]["dangling"] == 1


def test_rag_estimate_insufficient_context(rag_client: TestClient) -> None:
    insufficient = RagEstimationResult(
        summary="Insufficient retrieved context to produce a grounded estimation.",
        line_items=[],
        total_hours=0.0,
        insufficient_context=True,
    )
    app.dependency_overrides[rag_estimations.get_rag_estimation_service] = lambda: _FakeRagService(  # type: ignore[return-value]
        RagEstimationOutcome(
            result=insufficient,
            report=CitationReport(
                request_id="req_test",
                lines=[],
                counts={status: 0 for status in CitationLineStatus},
                has_dangling=False,
                has_integrity_violation=False,
            ),
            coherence_report=CoherenceReport(
                request_id="req_test",
                lines=[],
                counts={status: 0 for status in CoherenceLineStatus},
                has_violations=False,
            ),
            hallucination_report=HallucinationReport(
                request_id="req_test",
                lines=[],
                counts={grade: 0 for grade in HallucinationLineGrade},
                has_degraded=False,
            ),
            chunk_texts=[],
            model=None,
            provider=None,
            usage=None,
            finish_reason=None,
            prompt_version="estimation/rag/v1",
        )
    )

    response = rag_client.post(RAG_PATH, json={"question": "Unknown domain"})

    assert response.status_code == 200
    assert response.json()["result"]["insufficient_context"] is True
    assert response.json()["coherence_summary"]["has_violations"] is False


def test_rag_estimate_reports_hallucination_summary_when_degraded(rag_client: TestClient) -> None:
    from app.schemas.hallucination_report import HallucinationLineReport

    result = _grounded_result()
    degraded_report = HallucinationReport(
        request_id="req_test",
        lines=[
            HallucinationLineReport(
                index=0,
                component="authentication",
                grade=HallucinationLineGrade.DEGRADED,
                anchor_max=8.0,
            )
        ],
        counts={
            HallucinationLineGrade.GROUNDED: 0,
            HallucinationLineGrade.DEGRADED: 1,
            HallucinationLineGrade.INSUFFICIENT: 0,
        },
        has_degraded=True,
    )
    outcome = _outcome(result)
    outcome = RagEstimationOutcome(
        result=outcome.result,
        report=outcome.report,
        coherence_report=outcome.coherence_report,
        hallucination_report=degraded_report,
        chunk_texts=outcome.chunk_texts,
        model=outcome.model,
        provider=outcome.provider,
        usage=outcome.usage,
        finish_reason=outcome.finish_reason,
        prompt_version=outcome.prompt_version,
    )
    app.dependency_overrides[rag_estimations.get_rag_estimation_service] = lambda: _FakeRagService(  # type: ignore[return-value]
        outcome
    )

    response = rag_client.post(RAG_PATH, json={"question": "OAuth e-commerce platform"})

    assert response.status_code == 200
    body = response.json()
    assert body["hallucination_summary"]["has_degraded"] is True
    assert body["hallucination_summary"]["degraded"] == 1


def test_rag_estimate_provider_failure_returns_503(rag_client: TestClient) -> None:
    app.dependency_overrides[rag_estimations.get_rag_estimation_service] = lambda: _FakeRagService(  # type: ignore[return-value]
        error=StructuredCompletionError("provider down")
    )

    response = rag_client.post(RAG_PATH, json={"question": "OAuth e-commerce platform"})

    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"].lower()


def test_rag_estimate_rejects_empty_question(rag_client: TestClient) -> None:
    response = rag_client.post(RAG_PATH, json={"question": "   "})
    assert response.status_code == 422


def test_rag_estimate_rejects_empty_transcript(rag_client: TestClient) -> None:
    response = rag_client.post(
        RAG_PATH,
        json={"question": "OAuth e-commerce platform", "transcript": "   "},
    )
    assert response.status_code == 422


def test_rag_estimate_idempotency_key_returns_cached_response(rag_client: TestClient) -> None:
    from app.services.rag_idempotency import reset_idempotency_store

    reset_idempotency_store()
    calls = {"count": 0}
    result = _grounded_result()

    class _CountingFakeService:
        async def estimate(self, *args, **kwargs):
            calls["count"] += 1
            return _outcome(result)

    app.dependency_overrides[rag_estimations.get_rag_estimation_service] = lambda: _CountingFakeService()  # type: ignore[return-value]

    headers = {"Idempotency-Key": "idem-062-test"}
    first = rag_client.post(RAG_PATH, json={"question": "OAuth e-commerce platform"}, headers=headers)
    second = rag_client.post(RAG_PATH, json={"question": "OAuth e-commerce platform"}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["result"]["total_hours"] == second.json()["result"]["total_hours"]
    assert calls["count"] == 1
