"""Service helpers for explainable retrieval debug responses."""

from __future__ import annotations

from app.embedding_pipeline.retrieval_debug_schemas import (
    BranchResultEntry,
    ResultExplanation,
)
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


def filter_vector_branch_entries(
    entries: list[BranchResultEntry],
    *,
    threshold: float | None,
) -> list[BranchResultEntry]:
    """Keep vector entries whose normalized score satisfies the optional threshold."""

    if threshold is None:
        return entries
    return [entry for entry in entries if entry.score >= threshold]


def build_vector_explanation(
    entry: BranchResultEntry,
    *,
    threshold: float | None = None,
) -> ResultExplanation:
    """Build a vector-only explanation with stable debug signal names."""

    signals = ["semantic_strong" if entry.distance <= 0.4 else "semantic_weak"]
    if threshold is not None and entry.score < threshold:
        signals.append("below_threshold")

    if signals[0] == "semantic_strong":
        summary = "strong semantic match from the vector branch."
    else:
        summary = "weaker semantic match from the vector branch."
    if "below_threshold" in signals:
        summary = f"{summary} Similarity is below the configured threshold."

    return ResultExplanation(summary=summary, signals=signals)
