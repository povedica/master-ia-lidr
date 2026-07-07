"""Compare chunking strategies on sample budgets (feature-063)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.schemas import Budget, Chunk

SUPPORTED_STRATEGIES = ("structural", "recursive", "sentence_window")
_DEFAULT_EMBEDDING_COST_PER_1K = 0.00002


@dataclass(frozen=True)
class StrategyStats:
    strategy: str
    chunk_count: int
    avg_chunk_chars: int
    total_tokens_estimate: int
    estimated_embedding_cost_usd: float


@dataclass(frozen=True)
class StrategyQueryPreview:
    strategy: str
    query: str
    top_chunks: list[dict[str, object]]


def _recursive_chunks(budgets: list[Budget], *, max_chars: int = 600) -> list[Chunk]:
    structural = JSONStructuralChunker().chunk(budgets)
    out: list[Chunk] = []
    for index, chunk in enumerate(structural):
        text = chunk.text
        start = 0
        part = 0
        while start < len(text):
            end = min(len(text), start + max_chars)
            slice_text = text[start:end].strip()
            if slice_text:
                out.append(
                    Chunk(
                        chunk_id=f"{chunk.chunk_id}:r{part}",
                        text=slice_text,
                        metadata=dict(chunk.metadata),
                        token_count=max(1, len(slice_text.split())),
                    )
                )
                part += 1
            start = end
    return out


def _sentence_window_chunks(budgets: list[Budget], *, window: int = 3) -> list[Chunk]:
    structural = JSONStructuralChunker().chunk(budgets)
    out: list[Chunk] = []
    for chunk in structural:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", chunk.text) if s.strip()]
        for index in range(0, len(sentences), window):
            window_text = " ".join(sentences[index : index + window]).strip()
            if not window_text:
                continue
            out.append(
                Chunk(
                    chunk_id=f"{chunk.chunk_id}:w{index // window}",
                    text=window_text,
                    metadata=dict(chunk.metadata),
                    token_count=max(1, len(window_text.split())),
                )
            )
    return out


def chunk_budgets_for_strategy(strategy: str, budgets: list[Budget]) -> list[Chunk]:
    if strategy == "structural":
        return JSONStructuralChunker().chunk(budgets)
    if strategy == "recursive":
        return _recursive_chunks(budgets)
    if strategy == "sentence_window":
        return _sentence_window_chunks(budgets)
    raise KeyError(strategy)


def compute_strategy_stats(strategy: str, budgets: list[Budget]) -> StrategyStats:
    chunks = chunk_budgets_for_strategy(strategy, budgets)
    total_chars = sum(len(chunk.text) for chunk in chunks)
    total_tokens = sum(chunk.token_count for chunk in chunks)
    avg_chars = int(total_chars / len(chunks)) if chunks else 0
    cost = (total_tokens / 1000.0) * _DEFAULT_EMBEDDING_COST_PER_1K
    return StrategyStats(
        strategy=strategy,
        chunk_count=len(chunks),
        avg_chunk_chars=avg_chars,
        total_tokens_estimate=total_tokens,
        estimated_embedding_cost_usd=round(cost, 6),
    )


async def preview_strategy_queries(
    strategy: str,
    budgets: list[Budget],
    queries: list[str],
    *,
    embedder: OpenAIEmbedder,
    top_k: int,
) -> list[StrategyQueryPreview]:
    chunks = chunk_budgets_for_strategy(strategy, budgets)
    if not chunks:
        return [StrategyQueryPreview(strategy=strategy, query=query, top_chunks=[]) for query in queries]

    embedded = await embedder.embed_many(chunks)
    previews: list[StrategyQueryPreview] = []
    for query in queries:
        query_vector = await embedder.embed_one(query)

        def cosine(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(x * x for x in b) ** 0.5
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

        ranked = sorted(
            embedded,
            key=lambda row: cosine(query_vector, row.embedding),
            reverse=True,
        )[:top_k]
        previews.append(
            StrategyQueryPreview(
                strategy=strategy,
                query=query,
                top_chunks=[
                    {
                        "chunk_id": row.chunk_id,
                        "score": round(cosine(query_vector, row.embedding), 4),
                        "preview": row.text[:240],
                    }
                    for row in ranked
                ],
            )
        )
    return previews
