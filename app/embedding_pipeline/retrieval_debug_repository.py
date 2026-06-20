"""Persistence helpers for retrieval debug chunk inspection."""

from __future__ import annotations

from sqlalchemy import Select, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.retrieval_debug_schemas import ChunkInspectionResponse
from app.models.chunk import Chunk as ChunkModel
from app.models.document import Document as DocumentModel


class RetrievalDebugRepository:
    """Read persisted chunks and surrounding context for debug inspection."""

    def build_chunk_distance_statement(
        self,
        *,
        chunk_id: int,
        query_vector: list[float],
    ) -> Select[tuple[float]]:
        distance = ChunkModel.embedding.cosine_distance(query_vector).label("distance")
        return (
            select(distance)
            .where(ChunkModel.id == chunk_id)
            .where(ChunkModel.embedding.is_not(None))
        )

    async def get_chunk_distance(
        self,
        session: AsyncSession,
        *,
        chunk_id: int,
        query_vector: list[float],
    ) -> float | None:
        result = await session.execute(
            self.build_chunk_distance_statement(
                chunk_id=chunk_id,
                query_vector=query_vector,
            )
        )
        distance = result.scalar_one_or_none()
        return float(distance) if distance is not None else None

    async def get_chunk_inspection(
        self,
        session: AsyncSession,
        *,
        chunk_id: int,
        embedding_model: str,
    ) -> ChunkInspectionResponse | None:
        result = await session.execute(
            select(ChunkModel, DocumentModel)
            .join(DocumentModel, ChunkModel.document_id == DocumentModel.id)
            .where(ChunkModel.id == chunk_id)
        )
        row = result.one_or_none()
        if row is None:
            return None

        chunk, document = row
        previous_chunk = await self._get_neighbor_chunk(
            session,
            document_id=chunk.document_id,
            chunk_id=chunk.id,
            previous=True,
        )
        next_chunk = await self._get_neighbor_chunk(
            session,
            document_id=chunk.document_id,
            chunk_id=chunk.id,
            previous=False,
        )

        return ChunkInspectionResponse(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            content=chunk.content,
            chunk_type=chunk.chunk_type,
            metadata=chunk.metadata_,
            embedding_model=embedding_model,
            embedding_present=chunk.embedding is not None,
            document={
                "id": document.id,
                "source_path": document.source_path,
                "document_type": document.document_type,
                "metadata": document.metadata_,
            },
            previous_chunk=previous_chunk,
            next_chunk=next_chunk,
        )

    async def _get_neighbor_chunk(
        self,
        session: AsyncSession,
        *,
        document_id: int,
        chunk_id: int,
        previous: bool,
    ) -> dict[str, object] | None:
        operator = ChunkModel.id < chunk_id if previous else ChunkModel.id > chunk_id
        ordering = desc(ChunkModel.id) if previous else ChunkModel.id.asc()
        result = await session.execute(
            select(ChunkModel.id, ChunkModel.chunk_type, ChunkModel.content)
            .where(ChunkModel.document_id == document_id)
            .where(operator)
            .order_by(ordering)
            .limit(1)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return {
            "chunk_id": row.id,
            "chunk_type": row.chunk_type,
            "content_excerpt": " ".join(row.content.split())[:240],
        }
