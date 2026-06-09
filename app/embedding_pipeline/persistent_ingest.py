"""Transactional persisted ingest orchestration."""

from __future__ import annotations

import logging
import time

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.errors import DuplicateDocumentError
from app.embedding_pipeline.repository import (
    EMBEDDING_DIMENSION,
    EmbeddingIngestRepository,
)
from app.embedding_pipeline.schemas import EmbeddedChunk, PersistentIngestRequest, PersistentIngestResponse

logger = logging.getLogger(__name__)


async def run_persistent_ingest(
    request: PersistentIngestRequest,
    *,
    session: AsyncSession,
    chunker: JSONStructuralChunker,
    embedder: OpenAIEmbedder,
    repository: EmbeddingIngestRepository | None = None,
) -> PersistentIngestResponse:
    """Persist one budget document, its chunks, and embeddings atomically."""

    repo = repository or EmbeddingIngestRepository()
    started = time.perf_counter()

    existing_id = await repo.find_document_id_by_source_path(session, request.source_path)
    if existing_id is not None:
        raise DuplicateDocumentError(existing_id, request.source_path)

    chunks = chunker.chunk([request.content])
    embedded: list[EmbeddedChunk] = []
    if chunks:
        embedded = await embedder.embed_many(chunks)

    try:
        document_id = await repo.insert_document(
            session,
            source_path=request.source_path,
            document_type=request.document_type,
            metadata=request.metadata,
        )
        chunks_created = 0
        if embedded:
            chunks_created = await repo.insert_chunks(
                session,
                document_id=document_id,
                embedded_chunks=embedded,
            )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raced_id = await repo.find_document_id_by_source_path(session, request.source_path)
        if raced_id is not None:
            raise DuplicateDocumentError(raced_id, request.source_path)
        raise
    except Exception:
        await session.rollback()
        raise

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "persistent_ingest_completed",
        extra={
            "source_path": request.source_path,
            "document_type": request.document_type,
            "document_id": document_id,
            "chunks_created": chunks_created,
        },
    )
    return PersistentIngestResponse(
        document_id=document_id,
        chunks_created=chunks_created,
        embedding_dimension=EMBEDDING_DIMENSION,
        ingestion_time_ms=elapsed_ms,
    )
