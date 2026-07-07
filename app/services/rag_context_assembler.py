"""Build serialized retrieval context blocks for RAG estimation prompts."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import tiktoken

from app.embedding_pipeline.chunk_content_repository import ChunkContent
from app.embedding_pipeline.retrieval_schemas import RetrievalResultRow

logger = logging.getLogger(__name__)

_CHUNK_BLOCK_PATTERN = re.compile(
    r"\[CHUNK START\].*?\[CHUNK END\]",
    re.DOTALL,
)
_CHUNK_ID_PATTERN = re.compile(r"^chunk_id:\s*(\d+)\s*$", re.MULTILINE)


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


def _split_chunk_blocks(text: str) -> list[str]:
    if not text.strip():
        return []
    return _CHUNK_BLOCK_PATTERN.findall(text)


def truncate_to_token_budget(
    text: str,
    *,
    max_tokens: int,
    encoding: tiktoken.Encoding,
) -> str:
    """Drop tail chunk blocks until the serialized context fits the token budget."""

    if max_tokens <= 0 or not text.strip():
        return ""

    kept_blocks: list[str] = []
    for block in _split_chunk_blocks(text):
        candidate = "\n\n".join([*kept_blocks, block]) if kept_blocks else block
        if len(encoding.encode(candidate)) <= max_tokens:
            kept_blocks.append(block)
            continue
        break

    return "\n\n".join(kept_blocks)


def truncate_assembled_context(
    assembled: AssembledContext,
    *,
    max_tokens: int,
    encoding: tiktoken.Encoding,
) -> AssembledContext:
    """Truncate assembled RAG context at chunk boundaries and sync metadata."""

    truncated_block = truncate_to_token_budget(
        assembled.prompt_block,
        max_tokens=max_tokens,
        encoding=encoding,
    )
    if not truncated_block:
        return AssembledContext(prompt_block="", chunk_ids=set(), chunk_texts=[])

    original_blocks = _split_chunk_blocks(assembled.prompt_block)
    text_by_id: dict[int, str] = {}
    for block, text in zip(original_blocks, assembled.chunk_texts, strict=True):
        match = _CHUNK_ID_PATTERN.search(block)
        if match is not None:
            text_by_id[int(match.group(1))] = text

    surviving_ids: list[int] = []
    for match in _CHUNK_ID_PATTERN.finditer(truncated_block):
        surviving_ids.append(int(match.group(1)))

    return AssembledContext(
        prompt_block=truncated_block,
        chunk_ids=set(surviving_ids),
        chunk_texts=[text_by_id[chunk_id] for chunk_id in surviving_ids],
    )
