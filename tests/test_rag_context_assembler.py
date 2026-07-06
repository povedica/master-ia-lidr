"""Unit tests for RAG context assembly (FR-05)."""

from __future__ import annotations

from app.embedding_pipeline.chunk_content_repository import ChunkContent
from app.embedding_pipeline.retrieval_schemas import RetrievalResultRow
from app.services.rag_context_assembler import assemble_rag_context


def _row(chunk_id: int, document_id: int = 7, budget_id: str | None = "BUD-2024-014") -> RetrievalResultRow:
    return RetrievalResultRow(
        final_position=1,
        chunk_id=chunk_id,
        document_id=document_id,
        budget_id=budget_id,
        score=0.9,
        vector_score=0.1,
        lexical_score=0.2,
        fusion_score=0.15,
        rerank_score=0.9,
        matched_terms=["stripe"],
        source_strategies=["vector"],
        metadata={"budget_id": budget_id},
    )


def test_assemble_rag_context_chunk_ids_match_prompt_block() -> None:
    rows = [_row(42), _row(43, document_id=8, budget_id="BUD-2024-032")]
    contents = {
        42: ChunkContent(
            chunk_id=42,
            document_id=7,
            budget_id="BUD-2024-014",
            content="OAuth2 login flow",
            metadata={"budget_id": "BUD-2024-014"},
        ),
        43: ChunkContent(
            chunk_id=43,
            document_id=8,
            budget_id="BUD-2024-032",
            content="Stripe checkout integration",
            metadata={"budget_id": "BUD-2024-032"},
        ),
    }

    assembled = assemble_rag_context(rows, contents)

    assert assembled.chunk_ids == {42, 43}
    assert "chunk_id: 42" in assembled.prompt_block
    assert "chunk_id: 43" in assembled.prompt_block
    assert "[CHUNK START]" in assembled.prompt_block
    assert "[CHUNK END]" in assembled.prompt_block
    assert assembled.chunk_texts == ["OAuth2 login flow", "Stripe checkout integration"]


def test_assemble_rag_context_skips_missing_content(caplog) -> None:
    rows = [_row(42), _row(99)]
    contents = {
        42: ChunkContent(
            chunk_id=42,
            document_id=7,
            budget_id="BUD-2024-014",
            content="OAuth2 login flow",
            metadata={},
        ),
    }

    with caplog.at_level("WARNING"):
        assembled = assemble_rag_context(rows, contents)

    assert assembled.chunk_ids == {42}
    assert "99" not in assembled.prompt_block
    assert any("99" in record.message or "missing" in record.message.lower() for record in caplog.records)
