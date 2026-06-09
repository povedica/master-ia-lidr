"""Persistence helpers for embedding ingest."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.schemas import EmbeddedChunk
from app.models.chunk import Chunk as ChunkModel
from app.models.document import Document

CHUNK_TYPE_BUDGET_COMPONENT = "budget_component"
EMBEDDING_DIMENSION = 1536


class EmbeddingIngestRepository:
    """Read/write access for persisted budget documents and chunk embeddings."""

    async def find_document_id_by_source_path(
        self,
        session: AsyncSession,
        source_path: str,
    ) -> int | None:
        result = await session.execute(
            select(Document.id).where(Document.source_path == source_path)
        )
        return result.scalar_one_or_none()

    async def insert_document(
        self,
        session: AsyncSession,
        *,
        source_path: str,
        document_type: str,
        metadata: dict[str, object],
    ) -> int:
        document = Document(
            source_path=source_path,
            document_type=document_type,
            metadata_=metadata,
        )
        session.add(document)
        await session.flush()
        return document.id

    async def insert_chunks(
        self,
        session: AsyncSession,
        *,
        document_id: int,
        embedded_chunks: list[EmbeddedChunk],
    ) -> int:
        for embedded in embedded_chunks:
            session.add(
                ChunkModel(
                    document_id=document_id,
                    chunk_type=CHUNK_TYPE_BUDGET_COMPONENT,
                    content=embedded.text,
                    embedding=embedded.embedding,
                    metadata_=embedded.metadata,
                )
            )
        await session.flush()
        return len(embedded_chunks)
