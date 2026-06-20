"""Service helpers for explainable retrieval debug responses."""

from __future__ import annotations

from app.embedding_pipeline.retrieval_debug_schemas import BranchResultEntry
from app.embedding_pipeline.schemas import SearchResult


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, value))


def build_vector_branch_entries(results: list[SearchResult]) -> list[BranchResultEntry]:
    """Expose existing semantic-search results as ranked vector-branch entries."""

    return [
        BranchResultEntry(
            rank=index,
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            score=_clamp_score(1.0 - result.distance),
            distance=result.distance,
        )
        for index, result in enumerate(results, start=1)
    ]
