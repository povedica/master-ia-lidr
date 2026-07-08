"""Unit tests for RAG context augmentation (feature-053 FR-10)."""

from __future__ import annotations

from app.embedding_pipeline.chunk_content_repository import ChunkContent
from app.embedding_pipeline.rag_augmentation import (
    augment_retrieval_chunks,
    augment_stage_chunks,
    extract_key_points,
    reorder_edge_loaded_ids,
)
from app.embedding_pipeline.retrieval_schemas import RetrievalResultRow
from app.schemas.rag_stages import StageChunkView


def _row(chunk_id: int) -> RetrievalResultRow:
    return RetrievalResultRow(
        final_position=chunk_id,
        chunk_id=chunk_id,
        document_id=10,
        score=1.0 - chunk_id * 0.1,
    )


def _content(chunk_id: int, text: str) -> ChunkContent:
    return ChunkContent(
        chunk_id=chunk_id,
        document_id=10,
        budget_id=f"BUD-{chunk_id}",
        content=text,
        metadata={},
    )


def test_extract_key_points_keeps_figures_and_ids_drops_filler() -> None:
    text = "Intro prose with no data\nAUTH-001 :: OAuth backend — 120 h\nmore filler"
    key = extract_key_points(text)
    assert "AUTH-001 :: OAuth backend — 120 h" in key
    assert "Intro prose" not in key


def test_extract_key_points_never_empties_a_chunk() -> None:
    assert extract_key_points("just some prose") == "just some prose"


def test_reorder_edge_loaded_puts_strongest_at_both_ends() -> None:
    ids = list(range(5))
    reordered = reorder_edge_loaded_ids(ids)
    assert reordered[0] == 0
    assert reordered[-1] == 1
    assert reordered == [0, 2, 4, 3, 1]


def test_augment_retrieval_chunks_preserves_ids_and_strips_filler() -> None:
    rows = [_row(i) for i in range(4)]
    contents = {
        i: _content(i, f"ITEM-{i} :: work — {i * 10} h\nfiller")
        for i in range(4)
    }
    out_rows, out_contents = augment_retrieval_chunks(rows, contents, compress=True, reorder=True)
    assert sorted(r.chunk_id for r in out_rows) == [0, 1, 2, 3]
    assert all("filler" not in out_contents[i].content for i in range(4))


def test_augment_stage_chunks_matches_retrieval_behavior() -> None:
    chunks = [
        StageChunkView(
            chunk_id=i + 1,
            document_id=10,
            content=f"ITEM-{i} :: work — {i * 10} h\nfiller",
            collection="budgets",
        )
        for i in range(4)
    ]
    augmented = augment_stage_chunks(chunks, compress=True, reorder=True)
    assert sorted(c.chunk_id for c in augmented) == [1, 2, 3, 4]
    assert all("filler" not in c.content for c in augmented)


def test_augment_retrieval_chunks_noop_when_flags_off() -> None:
    rows = [_row(1)]
    contents = {1: _content(1, "plain text")}
    out_rows, out_contents = augment_retrieval_chunks(rows, contents, compress=False, reorder=False)
    assert out_rows == rows
    assert out_contents[1] == contents[1]
