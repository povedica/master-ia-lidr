"""Session 11 context augmentation: compress and edge-load retrieved chunks (FR-10)."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from app.embedding_pipeline.chunk_content_repository import ChunkContent
from app.embedding_pipeline.retrieval_schemas import RetrievalResultRow
from app.schemas.rag_stages import StageChunkView


def extract_key_points(content: str) -> str:
    """Keep lines with figures or id-like tokens; drop filler prose."""

    kept = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and (any(ch.isdigit() for ch in line) or "::" in line)
    ]
    if not kept:
        kept = [next((ln.strip() for ln in content.splitlines() if ln.strip()), "")]
    return "\n".join(kept)


def reorder_edge_loaded_ids(chunk_ids: list[int]) -> list[int]:
    """Place strongest chunks (best-first input) at both ends of the context."""

    head: list[int] = []
    tail: list[int] = []
    for index, chunk_id in enumerate(chunk_ids):
        (head if index % 2 == 0 else tail).append(chunk_id)
    return head + tail[::-1]


def augment_retrieval_chunks(
    rows: list[RetrievalResultRow],
    contents: Mapping[int, ChunkContent],
    *,
    compress: bool = True,
    reorder: bool = True,
) -> tuple[list[RetrievalResultRow], dict[int, ChunkContent]]:
    """Apply compress and edge-load reorder to retrieval rows and contents."""

    if not rows:
        return rows, dict(contents)

    working_contents = dict(contents)
    if compress:
        for chunk_id, content in working_contents.items():
            working_contents[chunk_id] = replace(
                content,
                content=extract_key_points(content.content),
            )

    ordered_rows = list(rows)
    if reorder:
        id_order = reorder_edge_loaded_ids([row.chunk_id for row in rows])
        by_id = {row.chunk_id: row for row in rows}
        ordered_rows = [by_id[chunk_id] for chunk_id in id_order]

    return ordered_rows, working_contents


def augment_stage_chunks(
    chunks: list[StageChunkView],
    *,
    compress: bool = True,
    reorder: bool = True,
) -> list[StageChunkView]:
    """Apply augmentation passes to stage wizard chunk payloads."""

    if not chunks:
        return chunks

    working = list(chunks)
    if compress:
        working = [
            chunk.model_copy(update={"content": extract_key_points(chunk.content)})
            for chunk in working
        ]
    if reorder:
        id_order = reorder_edge_loaded_ids([chunk.chunk_id for chunk in working])
        by_id = {chunk.chunk_id: chunk for chunk in working}
        working = [by_id[chunk_id] for chunk_id in id_order]
    return working
