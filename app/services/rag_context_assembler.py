"""Build serialized retrieval context blocks for RAG estimation prompts."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.embedding_pipeline.chunk_content_repository import ChunkContent
from app.embedding_pipeline.retrieval_schemas import RetrievalResultRow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssembledContext:
    prompt_block: str
    chunk_ids: set[int]
    chunk_texts: list[str]


def assemble_rag_context(
    rows: Sequence[RetrievalResultRow],
    contents: Mapping[int, ChunkContent],
) -> AssembledContext:
    """Serialize retrieved chunks into a deterministic prompt block."""

    blocks: list[str] = []
    chunk_ids: set[int] = set()
    chunk_texts: list[str] = []

    for row in rows:
        content = contents.get(row.chunk_id)
        if content is None:
            logger.warning(
                "rag_context_missing_chunk_content",
                extra={"chunk_id": row.chunk_id},
            )
            continue

        chunk_ids.add(row.chunk_id)
        chunk_texts.append(content.content)
        budget_line = f"budget_id: {content.budget_id}" if content.budget_id else "budget_id:"
        blocks.append(
            "\n".join(
                [
                    "[CHUNK START]",
                    f"chunk_id: {row.chunk_id}",
                    f"document_id: {row.document_id}",
                    budget_line,
                    "content:",
                    content.content,
                    "[CHUNK END]",
                ]
            )
        )

    return AssembledContext(
        prompt_block="\n\n".join(blocks),
        chunk_ids=chunk_ids,
        chunk_texts=chunk_texts,
    )
