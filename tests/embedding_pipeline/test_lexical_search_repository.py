"""Tests for lexical full-text search repository (feature-043)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.embedding_pipeline.lexical_search_repository import LexicalSearchRepository
from app.embedding_pipeline.retrieval_debug_schemas import RetrievalMetadataFilters


def test_lexical_search_statement_uses_postgres_full_text_ranking() -> None:
    repository = LexicalSearchRepository()

    statement = repository.build_search_statement(query="JWT OAuth2", top_k=7)

    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "websearch_to_tsquery" in compiled
    assert "to_tsvector" in compiled
    assert "ts_rank_cd" in compiled
    assert "@@" in compiled
    assert "ORDER BY ts_rank DESC" in compiled
    assert "LIMIT" in compiled


def test_lexical_search_statement_applies_metadata_filters_when_provided() -> None:
    repository = LexicalSearchRepository()
    filters = RetrievalMetadataFilters(
        document_type="historical_budget",
        client_sector="finance",
        tags=["backend"],
    )

    statement = repository.build_search_statement(
        query="JWT OAuth2",
        top_k=7,
        filters=filters,
    )

    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "JOIN documents" in compiled
    assert "chunks.metadata @>" in compiled
    assert "documents.document_type" in compiled
    assert "@@" in compiled


@pytest.mark.asyncio
async def test_search_chunks_maps_ranked_rows_to_lexical_results() -> None:
    repository = LexicalSearchRepository()
    row = SimpleNamespace(
        id=156,
        document_id=12,
        chunk_type="budget_component",
        content="JWT auth with OAuth2 refresh token rotation",
        metadata_={"scope": "backend"},
        ts_rank=0.42,
        matched_terms=["jwt", "oauth2"],
    )
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = [row]
    session.execute = AsyncMock(return_value=result)

    results = await repository.search_chunks(session, query="JWT OAuth2", top_k=5)

    assert len(results) == 1
    assert results[0].chunk_id == 156
    assert results[0].document_id == 12
    assert results[0].chunk_type == "budget_component"
    assert results[0].content == "JWT auth with OAuth2 refresh token rotation"
    assert results[0].metadata == {"scope": "backend"}
    assert results[0].ts_rank == pytest.approx(0.42)
    assert results[0].matched_terms == ["jwt", "oauth2"]
