"""Shared ingest orchestration for HTTP and CLI entry points."""

from __future__ import annotations

from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.schemas import Budget, IngestResponse, IngestStats


async def run_ingest(
    budgets: list[Budget],
    chunker: JSONStructuralChunker,
    embedder: OpenAIEmbedder,
) -> IngestResponse:
    """Chunk budgets, embed each chunk, and return vectors with aggregate stats."""

    chunks = chunker.chunk(budgets)
    embedded = await embedder.embed_many(chunks)
    return IngestResponse(
        chunks=embedded,
        stats=IngestStats(
            total_budgets=len(budgets),
            total_chunks=len(embedded),
            total_tokens=embedder.last_total_tokens,
            estimated_cost_usd=embedder.last_cost_usd,
        ),
    )
