"""Tests for retrieval debug API schemas (feature-042)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.embedding_pipeline.retrieval_debug_schemas import (
    BranchesContainer,
    BranchResultEntry,
    ChunkInspectionResponse,
    RetrievalDebugRequest,
    RetrievalDebugResponse,
    VectorBranchConfig,
)


def test_retrieval_debug_request_trims_query_and_defaults_vector_config() -> None:
    request = RetrievalDebugRequest(query="  OAuth refresh token rotation  ")

    assert request.query == "OAuth refresh token rotation"
    assert request.strategies == ["vector"]
    assert request.vector == VectorBranchConfig()
    assert request.max_results == 10


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"query": "   "}, "query"),
        ({"query": "valid", "strategies": []}, "strategies"),
        ({"query": "valid", "strategies": ["graph"]}, "strategies"),
        ({"query": "valid", "strategies": ["all", "vector"]}, "strategies"),
        ({"query": "valid", "vector": {"top_k": 0}}, "vector.top_k"),
        ({"query": "valid", "vector": {"top_k": 51}}, "vector.top_k"),
        ({"query": "valid", "vector": {"threshold": -0.1}}, "vector.threshold"),
        ({"query": "valid", "vector": {"threshold": 1.1}}, "vector.threshold"),
        ({"query": "valid", "max_results": 0}, "max_results"),
        ({"query": "valid", "max_results": 51}, "max_results"),
    ],
)
def test_retrieval_debug_request_rejects_invalid_input(
    payload: dict[str, object],
    field: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        RetrievalDebugRequest.model_validate(payload)

    error_locations = {".".join(str(part) for part in error["loc"]) for error in exc_info.value.errors()}
    assert field in error_locations


def test_branches_container_keeps_future_branches_nullable() -> None:
    vector_entry = BranchResultEntry(
        rank=1,
        chunk_id=156,
        document_id=12,
        score=0.8,
        distance=0.2,
    )

    branches = BranchesContainer(vector=[vector_entry])

    assert branches.vector == [vector_entry]
    assert branches.lexical is None
    assert branches.hybrid is None
    assert branches.rerank is None


def test_retrieval_debug_response_shape_accepts_empty_vector_results() -> None:
    response = RetrievalDebugResponse(
        query="OAuth backend",
        applied_config={"strategies": ["vector"], "max_results": 10},
        timings_ms={"vector": 0, "total": 1},
        warnings=[],
        branches=BranchesContainer(vector=[]),
        final_results=[],
    )

    assert response.branches.vector == []
    assert response.final_results == []


def test_chunk_inspection_response_exposes_document_and_embedding_metadata() -> None:
    response = ChunkInspectionResponse(
        chunk_id=156,
        document_id=12,
        content="Backend OAuth implementation",
        chunk_type="budget_component",
        metadata={"component_id": "AUTH-001"},
        embedding_model="text-embedding-3-small",
        embedding_present=True,
        document={
            "id": 12,
            "source_path": "data/budgets/example.json",
            "document_type": "historical_budget",
            "metadata": {"budget_id": "BUD-2024-014"},
        },
        previous_chunk=None,
        next_chunk=None,
        distance=None,
        similarity=None,
    )

    assert response.embedding_present is True
    assert response.document["source_path"] == "data/budgets/example.json"
