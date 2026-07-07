"""Persist generic text corpus segments (transcripts, technical docs)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.errors import DuplicateDocumentError
from app.embedding_pipeline.repository import EmbeddingIngestRepository
from app.embedding_pipeline.schemas import Chunk, EmbeddedChunk

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TextCorpusIngestResult:
    document_id: int
    chunks_created: int
    elapsed_ms: int


def segments_to_chunks(
    segments: list[object],
    *,
    chunk_type: str,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for segment in segments:
        content = getattr(segment, "content")
        metadata = dict(getattr(segment, "metadata"))
        metadata["chunk_type"] = chunk_type
        segment_id = getattr(segment, "segment_id")
        chunks.append(
            Chunk(
                chunk_id=segment_id,
                text=content,
                metadata=metadata,
                token_count=max(1, len(str(content).split())),
            )
        )
    return chunks


async def run_text_corpus_ingest(
    session: AsyncSession,
    *,
    source_path: str,
    document_type: str,
    collection: str,
    chunk_type: str,
    segments: list[object],
    embedder: OpenAIEmbedder,
    document_metadata: dict[str, object] | None = None,
    repository: EmbeddingIngestRepository | None = None,
) -> TextCorpusIngestResult:
    repo = repository or EmbeddingIngestRepository()
    started = time.perf_counter()

    existing_id = await repo.find_document_id_by_source_path(session, source_path)
    if existing_id is not None:
        raise DuplicateDocumentError(existing_id, source_path)

    chunks = segments_to_chunks(segments, chunk_type=chunk_type)
    embedded: list[EmbeddedChunk] = []
    if chunks:
        embedded = await embedder.embed_many(chunks)

    try:
        document_id = await repo.insert_document(
            session,
            source_path=source_path,
            document_type=document_type,
            metadata=document_metadata or {},
        )
        chunks_created = 0
        if embedded:
            chunks_created = await repo.insert_chunks(
                session,
                document_id=document_id,
                embedded_chunks=embedded,
                collection=collection,
                chunk_type=chunk_type,
            )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raced_id = await repo.find_document_id_by_source_path(session, source_path)
        if raced_id is not None:
            raise DuplicateDocumentError(raced_id, source_path)
        raise
    except Exception:
        await session.rollback()
        raise

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "text_corpus_ingest_completed",
        extra={
            "source_path": source_path,
            "collection": collection,
            "document_id": document_id,
            "chunks_created": chunks_created,
        },
    )
    return TextCorpusIngestResult(
        document_id=document_id,
        chunks_created=chunks_created,
        elapsed_ms=elapsed_ms,
    )
