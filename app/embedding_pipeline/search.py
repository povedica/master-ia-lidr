"""Semantic search orchestration over persisted chunk embeddings."""

from __future__ import annotations

import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.schemas import SearchRequest, SearchResponse
from app.embedding_pipeline.search_repository import SemanticSearchRepository

logger = logging.getLogger(__name__)


async def run_semantic_search(
    request: SearchRequest,
    *,
    session: AsyncSession,
    embedder: OpenAIEmbedder,
    repository: SemanticSearchRepository | None = None,
) -> SearchResponse:
    """Embed the query and return the top-k persisted chunks by cosine distance."""

    repo = repository or SemanticSearchRepository()
    started = time.perf_counter()

    query_vector = await embedder.embed_one(request.query)
    results = await repo.search_chunks(session, query_vector=query_vector, k=request.k)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "semantic_search_completed",
        extra={
            "k": request.k,
            "result_count": len(results),
            "search_time_ms": elapsed_ms,
        },
    )
    return SearchResponse(
        query=request.query,
        k=request.k,
        search_time_ms=elapsed_ms,
        results=results,
    )
