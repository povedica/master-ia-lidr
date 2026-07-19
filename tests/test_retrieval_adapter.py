"""Tests for agentic retrieval adapter mapping."""

from __future__ import annotations

from app.embedding_pipeline.chunk_content_repository import ChunkContent
from app.embedding_pipeline.retrieval_schemas import RetrievalResultRow
from app.services.agentic.retrieval_adapter import map_retrieval_row_to_item


def test_maps_retrieval_row_to_historical_item() -> None:
    row = RetrievalResultRow(
        final_position=1,
        chunk_id=1001,
        document_id=7,
        budget_id="BUD-CORE-2023-02",
        score=0.12,
        fusion_score=0.12,
        metadata={"client_sector": "logistics", "estimated_hours": 1150},
    )
    content = ChunkContent(
        chunk_id=1001,
        document_id=7,
        budget_id="BUD-CORE-2023-02",
        content="Backend de negocio con API REST para pedidos y rutas.",
        metadata={"client_sector": "logistics", "estimated_hours": 1150},
    )

    item = map_retrieval_row_to_item(row, content)

    assert item["id"] == 1001
    assert item["sector"] == "logistics"
    assert item["budget_id"] == "BUD-CORE-2023-02"
    assert item["estimated_hours"] == 1150.0
    assert item["distance"] == 0.12
    assert "Backend de negocio" in item["content_preview"]


def test_maps_row_without_content_uses_row_metadata() -> None:
    row = RetrievalResultRow(
        final_position=1,
        chunk_id=42,
        document_id=3,
        budget_id=None,
        score=0.5,
        metadata={"client_sector": "finance", "estimated_hours": 420, "budget_id": "BUD-AUTH"},
    )

    item = map_retrieval_row_to_item(row, None)

    assert item["estimated_hours"] == 420.0
    assert item["sector"] == "finance"
    assert item["budget_id"] == "BUD-AUTH"
