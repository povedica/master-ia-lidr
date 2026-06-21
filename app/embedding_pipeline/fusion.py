"""Pure ranking fusion helpers for retrieval debug diagnostics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.embedding_pipeline.retrieval_debug_schemas import BranchResultEntry

BranchRankings = Mapping[str, Sequence[BranchResultEntry]]


def _normalized_weights(
    branch_names: Sequence[str],
    weights: Mapping[str, float] | None,
) -> dict[str, float]:
    if not branch_names:
        return {}

    raw_weights = {
        branch_name: weights.get(branch_name, 1.0) if weights is not None else 1.0
        for branch_name in branch_names
    }
    if any(weight < 0 for weight in raw_weights.values()):
        raise ValueError("fusion weights must be greater than or equal to zero")

    total = sum(raw_weights.values())
    if total <= 0:
        raise ValueError("at least one fusion weight must be greater than zero")

    return {
        branch_name: weight / total
        for branch_name, weight in raw_weights.items()
    }


def _entry_metadata(branch_rankings: BranchRankings) -> dict[int, BranchResultEntry]:
    entries: dict[int, BranchResultEntry] = {}
    for ranking in branch_rankings.values():
        for entry in ranking:
            entries.setdefault(entry.chunk_id, entry)
    return entries


def _rank_fused_scores(
    scores: Mapping[int, float],
    metadata: Mapping[int, BranchResultEntry],
) -> list[BranchResultEntry]:
    ranked_chunk_ids = sorted(
        scores,
        key=lambda chunk_id: (-scores[chunk_id], chunk_id),
    )
    return [
        BranchResultEntry(
            rank=rank,
            chunk_id=chunk_id,
            document_id=metadata[chunk_id].document_id,
            score=scores[chunk_id],
        )
        for rank, chunk_id in enumerate(ranked_chunk_ids, start=1)
    ]


def reciprocal_rank_fusion(
    branch_rankings: BranchRankings,
    *,
    k: int = 60,
    weights: Mapping[str, float] | None = None,
) -> list[BranchResultEntry]:
    """Fuse branch rankings with Reciprocal Rank Fusion."""

    if k <= 0:
        raise ValueError("rrf k must be greater than zero")

    branch_names = list(branch_rankings)
    effective_weights = {
        branch_name: weights.get(branch_name, 1.0) if weights is not None else 1.0
        for branch_name in branch_names
    }
    if any(weight < 0 for weight in effective_weights.values()):
        raise ValueError("fusion weights must be greater than or equal to zero")

    scores: dict[int, float] = {}
    for branch_name, ranking in branch_rankings.items():
        branch_weight = effective_weights[branch_name]
        for entry in ranking:
            scores[entry.chunk_id] = scores.get(entry.chunk_id, 0.0) + (
                branch_weight / (k + entry.rank)
            )

    return _rank_fused_scores(scores, _entry_metadata(branch_rankings))


def weighted_fusion(
    branch_rankings: BranchRankings,
    *,
    weights: Mapping[str, float],
) -> list[BranchResultEntry]:
    """Fuse branch rankings by normalized branch scores and normalized weights."""

    effective_weights = _normalized_weights(list(branch_rankings), weights)
    scores: dict[int, float] = {}
    for branch_name, ranking in branch_rankings.items():
        branch_weight = effective_weights[branch_name]
        for entry in ranking:
            scores[entry.chunk_id] = scores.get(entry.chunk_id, 0.0) + (
                branch_weight * entry.score
            )

    return _rank_fused_scores(scores, _entry_metadata(branch_rankings))
