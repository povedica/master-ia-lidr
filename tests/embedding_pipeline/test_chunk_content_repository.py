"""Tests for chunk content repository (FR-04)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.embedding_pipeline.chunk_content_repository import ChunkContentRepository


def test_contents_by_ids_statement_filters_on_chunk_ids() -> None:
    repository = ChunkContentRepository()
    statement = repository.build_contents_by_ids_statement([42, 43])
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "chunks.id IN" in compiled


@pytest.mark.asyncio
async def test_get_contents_by_ids_maps_rows() -> None:
    repository = ChunkContentRepository()
    row = SimpleNamespace(
        id=42,
        document_id=7,
        content="Stripe OAuth2 integration scope",
        metadata_={"budget_id": "BUD-2024-014", "scope": "payments"},
    )
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    session.execute = AsyncMock(return_value=result)

    contents = await repository.get_contents_by_ids(session, [42, 999])

    assert set(contents.keys()) == {42}
    content = contents[42]
    assert content.document_id == 7
    assert content.budget_id == "BUD-2024-014"
    assert content.content == "Stripe OAuth2 integration scope"
    assert content.metadata["scope"] == "payments"


@pytest.mark.asyncio
async def test_get_contents_by_ids_empty_input_returns_empty_map() -> None:
    repository = ChunkContentRepository()
    session = AsyncMock()

    contents = await repository.get_contents_by_ids(session, [])

    assert contents == {}
    session.execute.assert_not_called()
