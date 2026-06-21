"""Persistence queries for lexical full-text search over chunk content."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import Select, bindparam, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.metadata_filters import (
    build_metadata_filters,
    metadata_filters_require_document_join,
)
from app.embedding_pipeline.retrieval_debug_schemas import RetrievalMetadataFilters
from app.models.chunk import Chunk as ChunkModel
from app.models.document import Document as DocumentModel

_HEADLINE_MATCH_RE = re.compile(r"<<([^<>]+)>>")


@dataclass(frozen=True)
class LexicalSearchResult:
    """One ranked chunk from Postgres full-text search."""

    chunk_id: int
    document_id: int
    chunk_type: str
    content: str
    metadata: dict[str, object]
    ts_rank: float
    matched_terms: list[str]


def _extract_highlighted_terms(headline: str) -> list[str]:
    terms = {
        match.strip().lower()
        for match in _HEADLINE_MATCH_RE.findall(headline)
        if match.strip()
    }
    return sorted(terms)


class LexicalSearchRepository:
    """Read ranked chunks by Postgres full-text match against chunk content."""

    def __init__(self, *, text_search_config: str = "spanish") -> None:
        self._text_search_config = text_search_config

    def build_search_statement(
        self,
        *,
        query: str,
        top_k: int,
        filters: RetrievalMetadataFilters | None = None,
    ) -> Select[tuple[int, int, str, str, dict[str, object], float, str]]:
        query_param = bindparam("query", query)
        ts_query = func.websearch_to_tsquery(self._text_search_config, query_param)
        document_vector = ChunkModel.content_tsv
        ts_rank = func.ts_rank_cd(document_vector, ts_query).label("ts_rank")
        headline = func.ts_headline(
            self._text_search_config,
            ChunkModel.content,
            ts_query,
            "StartSel=<<, StopSel=>>, MaxWords=35, MinWords=1",
        ).label("headline")

        statement = (
            select(
                ChunkModel.id,
                ChunkModel.document_id,
                ChunkModel.chunk_type,
                ChunkModel.content,
                ChunkModel.metadata_,
                ts_rank,
                headline,
            )
            .where(document_vector.op("@@")(ts_query))
            .order_by(desc(ts_rank))
            .limit(top_k)
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
        query: str,
        top_k: int,
        filters: RetrievalMetadataFilters | None = None,
    ) -> list[LexicalSearchResult]:
        statement = self.build_search_statement(
            query=query,
            top_k=top_k,
            filters=filters,
        )
        result = await session.execute(statement)
        rows = result.all()
        return [
            LexicalSearchResult(
                chunk_id=row.id,
                document_id=row.document_id,
                chunk_type=row.chunk_type,
                content=row.content,
                metadata=row.metadata_,
                ts_rank=float(row.ts_rank),
                matched_terms=list(
                    getattr(row, "matched_terms", None)
                    or _extract_highlighted_terms(getattr(row, "headline", ""))
                ),
            )
            for row in rows
        ]
