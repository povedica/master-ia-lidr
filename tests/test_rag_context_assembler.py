"""Unit tests for RAG context assembly (FR-05)."""

from __future__ import annotations

import tiktoken

from app.embedding_pipeline.chunk_content_repository import ChunkContent
from app.embedding_pipeline.retrieval_schemas import RetrievalResultRow
from app.services.rag_context_assembler import (
    assemble_rag_context,
    truncate_assembled_context,
    truncate_to_token_budget,
)

_ENCODER = tiktoken.get_encoding("cl100k_base")


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


def _chunk_block(chunk_id: int, content: str) -> str:
    return "\n".join(
        [
            "[CHUNK START]",
            f"chunk_id: {chunk_id}",
            "document_id: 7",
            "budget_id: BUD-2024-014",
            "content:",
            content,
            "[CHUNK END]",
        ]
    )


def test_truncate_to_token_budget_empty_returns_empty() -> None:
    assert truncate_to_token_budget("", max_tokens=10, encoding=_ENCODER) == ""


def test_truncate_to_token_budget_single_chunk_under_budget_unchanged() -> None:
    block = _chunk_block(42, "short content")
    assert truncate_to_token_budget(block, max_tokens=100, encoding=_ENCODER) == block


def test_truncate_to_token_budget_drops_tail_chunks_over_budget() -> None:
    first = _chunk_block(42, "alpha " * 20)
    second = _chunk_block(43, "beta " * 20)
    combined = f"{first}\n\n{second}"
    first_tokens = len(_ENCODER.encode(first))

    truncated = truncate_to_token_budget(
        combined,
        max_tokens=first_tokens + 5,
        encoding=_ENCODER,
    )

    assert truncated == first
    assert "chunk_id: 43" not in truncated
    assert truncated.count("[CHUNK START]") == 1
    assert truncated.count("[CHUNK END]") == 1


def test_truncate_to_token_budget_never_exceeds_max_tokens() -> None:
    blocks = [_chunk_block(index, f"content-{index} " * 30) for index in range(1, 6)]
    combined = "\n\n".join(blocks)
    max_tokens = 40

    truncated = truncate_to_token_budget(combined, max_tokens=max_tokens, encoding=_ENCODER)

    assert len(_ENCODER.encode(truncated)) <= max_tokens


def test_truncate_assembled_context_filters_chunk_ids_and_texts() -> None:
    rows = [_row(42), _row(43, document_id=8, budget_id="BUD-2024-032")]
    contents = {
        42: ChunkContent(
            chunk_id=42,
            document_id=7,
            budget_id="BUD-2024-014",
            content="OAuth2 login flow " * 30,
            metadata={"budget_id": "BUD-2024-014"},
        ),
        43: ChunkContent(
            chunk_id=43,
            document_id=8,
            budget_id="BUD-2024-032",
            content="Stripe checkout integration " * 30,
            metadata={"budget_id": "BUD-2024-032"},
        ),
    }
    assembled = assemble_rag_context(rows, contents)
    first_block_tokens = len(_ENCODER.encode(assembled.prompt_block.split("\n\n")[0]))

    truncated = truncate_assembled_context(
        assembled,
        max_tokens=first_block_tokens + 5,
        encoding=_ENCODER,
    )

    assert truncated.chunk_ids == {42}
    assert truncated.chunk_texts == [contents[42].content]
    assert "chunk_id: 43" not in truncated.prompt_block
