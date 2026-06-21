"""Tests for retrieval debug API schemas (feature-042)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.embedding_pipeline.retrieval_debug_schemas import (
    BranchesContainer,
    BranchResultEntry,
    ChunkInspectionResponse,
    DebugResult,
    HybridBranchConfig,
    LexicalBranchConfig,
    RankingDiffEntryResponse,
    RankingDiffResponse,
    RerankBranchConfig,
    ResultExplanation,
    RetrievalDebugRequest,
    RetrievalDebugResponse,
    VectorBranchConfig,
)


def test_retrieval_debug_request_trims_query_and_defaults_vector_config() -> None:
    request = RetrievalDebugRequest(query="  OAuth refresh token rotation  ")

    assert request.query == "OAuth refresh token rotation"
    assert request.strategies == ["vector"]
    assert request.vector == VectorBranchConfig()
    assert request.lexical == LexicalBranchConfig()
    assert request.max_results == 10


def test_retrieval_debug_request_accepts_lexical_config() -> None:
    request = RetrievalDebugRequest(
        query="JWT OAuth2",
        strategies=["lexical"],
        lexical={"top_k": 20},
    )

    assert request.strategies == ["lexical"]
    assert request.lexical.top_k == 20


def test_retrieval_debug_request_accepts_hybrid_config_defaults() -> None:
    request = RetrievalDebugRequest(query="JWT OAuth2", strategies=["hybrid"])

    assert request.hybrid == HybridBranchConfig()
    assert request.hybrid.enabled is True
    assert request.hybrid.method == "rrf"
    assert request.hybrid.rrf_k == 60
    assert request.hybrid.weights is None


def test_retrieval_debug_request_accepts_rerank_config_defaults() -> None:
    request = RetrievalDebugRequest(query="JWT OAuth2", strategies=["rerank"])

    assert request.rerank == RerankBranchConfig()
    assert request.rerank.enabled is False


def test_retrieval_debug_request_accepts_enabled_rerank_config() -> None:
    request = RetrievalDebugRequest(
        query="JWT OAuth2",
        strategies=["rerank"],
        rerank={"enabled": True},
    )

    assert request.rerank.enabled is True


def test_retrieval_debug_request_rejects_weighted_hybrid_without_weights() -> None:
    with pytest.raises(ValidationError) as exc_info:
        RetrievalDebugRequest.model_validate(
            {
                "query": "JWT OAuth2",
                "strategies": ["hybrid"],
                "hybrid": {"method": "weighted"},
            }
        )

    error_locations = {".".join(str(part) for part in error["loc"]) for error in exc_info.value.errors()}
    assert "hybrid" in error_locations


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
        ({"query": "valid", "lexical": {"top_k": 0}}, "lexical.top_k"),
        ({"query": "valid", "lexical": {"top_k": 51}}, "lexical.top_k"),
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


def test_branch_result_entry_accepts_lexical_matched_terms_without_distance() -> None:
    entry = BranchResultEntry(
        rank=1,
        chunk_id=156,
        document_id=12,
        score=1.0,
        matched_terms=["jwt", "oauth2"],
    )

    assert entry.distance is None
    assert entry.matched_terms == ["jwt", "oauth2"]


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


def test_debug_result_accepts_lexical_only_fields_with_nullable_semantic_fields() -> None:
    result = DebugResult(
        final_position=1,
        chunk_id=156,
        document_id=12,
        title="BUD-2024-014 AUTH-001",
        content_excerpt="JWT auth with OAuth2 refresh token rotation",
        semantic_score=None,
        semantic_rank=None,
        semantic_distance=None,
        lexical_score=1.0,
        lexical_rank=1,
        matched_terms=["jwt", "oauth2"],
        source_strategies=["lexical"],
        metadata={"component_id": "AUTH-001"},
        explanation=ResultExplanation(
            summary="exact lexical match from the full-text branch.",
            signals=["lexical_exact_match"],
        ),
    )

    assert result.semantic_score is None
    assert result.lexical_score == 1.0
    assert result.matched_terms == ["jwt", "oauth2"]


def test_debug_result_accepts_hybrid_fusion_fields() -> None:
    result = DebugResult(
        final_position=1,
        chunk_id=156,
        document_id=12,
        title="BUD-2024-014 AUTH-001",
        content_excerpt="JWT auth with OAuth2 refresh token rotation",
        fusion_score=0.82,
        fusion_rank=1,
        source_strategies=["vector", "lexical", "hybrid"],
        metadata={"component_id": "AUTH-001"},
        explanation=ResultExplanation(
            summary="branch consensus.",
            signals=["branch_consensus"],
        ),
    )

    assert result.fusion_score == 0.82
    assert result.fusion_rank == 1


def test_debug_result_accepts_rerank_fields() -> None:
    result = DebugResult(
        final_position=1,
        chunk_id=156,
        document_id=12,
        title="BUD-2024-014 AUTH-001",
        content_excerpt="JWT auth with OAuth2 refresh token rotation",
        rerank_score=None,
        rerank_rank=1,
        source_strategies=["vector", "lexical", "hybrid", "rerank"],
        metadata={"component_id": "AUTH-001"},
        explanation=ResultExplanation(
            summary="rerank placeholder kept the fused order.",
            signals=[],
        ),
    )

    assert result.rerank_score is None
    assert result.rerank_rank == 1


def test_retrieval_debug_response_accepts_ranking_diff() -> None:
    response = RetrievalDebugResponse(
        query="OAuth backend",
        applied_config={"strategies": ["hybrid"], "max_results": 10},
        timings_ms={"hybrid": 0, "total": 1},
        warnings=[],
        branches=BranchesContainer(hybrid=[]),
        final_results=[],
        diff=RankingDiffResponse(
            common=[
                RankingDiffEntryResponse(
                    chunk_id=156,
                    document_id=12,
                    source_strategies=["vector", "lexical"],
                    branch_ranks={"vector": 1, "lexical": 2},
                )
            ],
        ),
    )

    assert response.diff is not None
    assert response.diff.common[0].chunk_id == 156
    assert response.diff.dropped_by_rerank == []


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
