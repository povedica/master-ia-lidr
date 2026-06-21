"""Persistence queries for semantic search over pgvector chunk embeddings.

Uses HNSW index ``ix_chunks_embedding_hnsw`` (``vector_cosine_ops``) when the planner
selects ANN for ``cosine_distance`` queries — see migration ``0002`` and docs §24.
"""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.metadata_filters import (
    build_metadata_filters,
    metadata_filters_require_document_join,
)
from app.embedding_pipeline.retrieval_debug_schemas import RetrievalMetadataFilters
from app.embedding_pipeline.schemas import SearchResult
from app.models.chunk import Chunk as ChunkModel
from app.models.document import Document as DocumentModel


class SemanticSearchRepository:
    """Read ranked chunks by cosine distance to a query embedding."""

    def build_search_statement(
        self,
        *,
        query_vector: list[float],
        k: int,
        filters: RetrievalMetadataFilters | None = None,
    ) -> Select[tuple[int, int, str, str, dict[str, object], float]]:
        distance = ChunkModel.embedding.cosine_distance(query_vector).label("distance")
        statement = (
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
        if metadata_filters_require_document_join(filters):
            statement = statement.join(DocumentModel, ChunkModel.document_id == DocumentModel.id)
        for predicate in build_metadata_filters(filters):
            statement = statement.where(predicate)
        return statement

    async def search_chunks(
        self,
        session: AsyncSession,
        *,
        query_vector: list[float],
        k: int,
        filters: RetrievalMetadataFilters | None = None,
    ) -> list[SearchResult]:
        statement = self.build_search_statement(
            query_vector=query_vector,
            k=k,
            filters=filters,
        )
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
