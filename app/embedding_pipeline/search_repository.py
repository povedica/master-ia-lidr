"""Persistence queries for semantic search over pgvector chunk embeddings."""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.schemas import SearchResult
from app.models.chunk import Chunk as ChunkModel


class SemanticSearchRepository:
    """Read ranked chunks by cosine distance to a query embedding."""

    def build_search_statement(
        self,
        *,
        query_vector: list[float],
        k: int,
    ) -> Select[tuple[int, int, str, str, dict[str, object], float]]:
        distance = ChunkModel.embedding.cosine_distance(query_vector).label("distance")
        return (
            select(
                ChunkModel.id,
                ChunkModel.document_id,
                ChunkModel.chunk_type,
                ChunkModel.content,
                ChunkModel.metadata_,
                distance,
            )
            .where(ChunkModel.embedding.is_not(None))
            .order_by(distance)
            .limit(k)
        )

    async def search_chunks(
        self,
        session: AsyncSession,
        *,
        query_vector: list[float],
        k: int,
    ) -> list[SearchResult]:
        statement = self.build_search_statement(query_vector=query_vector, k=k)
        result = await session.execute(statement)
        rows = result.all()
        return [
            SearchResult(
                chunk_id=row.id,
                document_id=row.document_id,
                chunk_type=row.chunk_type,
                content=row.content,
                distance=float(row.distance),
                metadata=row.metadata_,
            )
            for row in rows
        ]
