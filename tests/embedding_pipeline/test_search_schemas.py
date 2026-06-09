"""Tests for semantic search request/response schemas (feature-038)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.embedding_pipeline.schemas import SearchRequest, SearchResponse, SearchResult


def test_search_request_defaults_k_to_five() -> None:
    request = SearchRequest(query="OAuth backend for fintech")
    assert request.query == "OAuth backend for fintech"
    assert request.k == 5


def test_search_request_strips_query_whitespace() -> None:
    request = SearchRequest(query="  REST API  ")
    assert request.query == "REST API"


def test_search_request_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        SearchRequest(query="")


def test_search_request_rejects_whitespace_only_query() -> None:
    with pytest.raises(ValidationError):
        SearchRequest(query="   ")


def test_search_request_rejects_k_below_one() -> None:
    with pytest.raises(ValidationError):
        SearchRequest(query="valid query", k=0)


def test_search_request_rejects_k_above_fifty() -> None:
    with pytest.raises(ValidationError):
        SearchRequest(query="valid query", k=51)


def test_search_result_serializes_metadata() -> None:
    result = SearchResult(
        chunk_id=156,
        document_id=12,
        chunk_type="budget_component",
        content="Backend service implementation",
        distance=0.231,
        metadata={"scope": "backend", "technologies": ["python", "fastapi"]},
    )
    assert result.chunk_id == 156
    assert result.metadata["scope"] == "backend"


def test_search_response_from_valid_data() -> None:
    response = SearchResponse(
        query="REST API with OAuth",
        k=5,
        search_time_ms=87,
        results=[
            SearchResult(
                chunk_id=1,
                document_id=2,
                chunk_type="budget_component",
                content="Example chunk",
                distance=0.12,
                metadata={},
            )
        ],
    )
    assert response.k == 5
    assert len(response.results) == 1
    assert response.search_time_ms == 87
