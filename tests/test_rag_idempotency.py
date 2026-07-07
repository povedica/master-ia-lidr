"""Unit tests for RAG estimate idempotency store (feature-062)."""

from __future__ import annotations

import time

from app.schemas.rag_estimation_response import (
    CitationSummaryView,
    CoherenceSummaryView,
    HallucinationSummaryView,
    RagEstimationResponse,
)
from app.schemas.rag_estimation_result import RagEstimationResult
from app.services.rag_idempotency import IdempotencyStore


def _sample_response() -> RagEstimationResponse:
    return RagEstimationResponse(
        result=RagEstimationResult(
            summary="Grounded estimate with enough words for validation.",
            line_items=[],
            total_hours=0.0,
        ),
        citation_summary=CitationSummaryView(
            grounded_ok=0,
            dangling=0,
            insufficient=0,
            integrity_violations=0,
            has_dangling=False,
        ),
        coherence_summary=CoherenceSummaryView(
            coherent_ok=0,
            total_hours_mismatch=0,
            duplicate_component=0,
            insufficient_context_violation=0,
            zero_hours_grounded=0,
            has_violations=False,
        ),
        hallucination_summary=HallucinationSummaryView(
            grounded=0,
            degraded=0,
            insufficient=0,
            has_degraded=False,
        ),
        request_id="req-1",
    )


def test_idempotency_store_round_trip_memory_backend() -> None:
    store = IdempotencyStore(redis_client=None, ttl_seconds=60)
    response = _sample_response()
    store.set("key-a", response)
    cached = store.get("key-a")
    assert cached is not None
    assert cached.request_id == "req-1"
    assert cached.result.summary == response.result.summary


def test_idempotency_store_miss_returns_none() -> None:
    store = IdempotencyStore(redis_client=None, ttl_seconds=60)
    assert store.get("missing") is None


def test_idempotency_store_expires_in_memory_backend() -> None:
    store = IdempotencyStore(redis_client=None, ttl_seconds=60)
    store.set("key-b", _sample_response())
    with store._lock:
        raw, _expires = store._mem["key-b"]
        store._mem["key-b"] = (raw, time.monotonic() - 1.0)
    assert store.get("key-b") is None
