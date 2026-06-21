"""Pure ranking fusion helpers for retrieval debug diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping, Sequence

from app.embedding_pipeline.retrieval_debug_schemas import BranchResultEntry, ResultExplanation

BranchRankings = Mapping[str, Sequence[BranchResultEntry]]
CONTROLLED_EXPLANATION_SIGNALS = {
    "semantic_strong",
    "semantic_weak",
    "lexical_exact_match",
    "branch_consensus",
    "hybrid_rescued",
    "below_threshold",
}


@dataclass(frozen=True)
class RankingDiffEntry:
    """One chunk classified by a ranking diff bucket."""

    chunk_id: int
    document_id: int
    source_strategies: list[str]
    branch_ranks: dict[str, int]


@dataclass(frozen=True)
class RankingMover:
    """One chunk whose fused rank moved materially from its best branch rank."""

    chunk_id: int
    document_id: int
    from_rank: int
    to_rank: int
    delta: int


@dataclass(frozen=True)
class RankingDiff:
    """Consensus and divergence sets between branch and fused rankings."""

    common: list[RankingDiffEntry] = field(default_factory=list)
    vector_only: list[RankingDiffEntry] = field(default_factory=list)
    lexical_only: list[RankingDiffEntry] = field(default_factory=list)
    hybrid_rescued: list[RankingDiffEntry] = field(default_factory=list)
    big_movers: list[RankingMover] = field(default_factory=list)
    dropped_by_threshold: list[RankingDiffEntry] = field(default_factory=list)
    dropped_by_rerank: list[RankingDiffEntry] = field(default_factory=list)


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


def _branch_ranks_by_chunk(branch_rankings: BranchRankings) -> dict[int, dict[str, int]]:
    ranks: dict[int, dict[str, int]] = {}
    for branch_name, ranking in branch_rankings.items():
        for entry in ranking:
            ranks.setdefault(entry.chunk_id, {})[branch_name] = entry.rank
    return ranks


def _entries_by_branch(branches: BranchRankings, chunk_id: int) -> dict[str, BranchResultEntry]:
    entries: dict[str, BranchResultEntry] = {}
    for branch_name, ranking in branches.items():
        for entry in ranking:
            if entry.chunk_id == chunk_id:
                entries[branch_name] = entry
                break
    return entries


def _diff_entry(
    chunk_id: int,
    *,
    ranks_by_chunk: Mapping[int, dict[str, int]],
    metadata: Mapping[int, BranchResultEntry],
) -> RankingDiffEntry:
    branch_ranks = ranks_by_chunk.get(chunk_id, {})
    return RankingDiffEntry(
        chunk_id=chunk_id,
        document_id=metadata[chunk_id].document_id,
        source_strategies=sorted(branch_ranks),
        branch_ranks=dict(sorted(branch_ranks.items())),
    )


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


def build_ranking_diff(
    branches: BranchRankings,
    final: Sequence[BranchResultEntry],
    *,
    threshold_drops: Sequence[int],
    rerank_drops: Sequence[int] | None = None,
    big_mover_threshold: int = 3,
    rescue_rank_threshold: int = 3,
) -> RankingDiff:
    """Build deterministic consensus/divergence buckets for branch diagnostics."""

    metadata = _entry_metadata(branches)
    ranks_by_chunk = _branch_ranks_by_chunk(branches)
    final_ranks = {entry.chunk_id: entry.rank for entry in final}

    def existing_entry(chunk_id: int) -> RankingDiffEntry:
        return _diff_entry(
            chunk_id,
            ranks_by_chunk=ranks_by_chunk,
            metadata=metadata,
        )

    common = [
        existing_entry(chunk_id)
        for chunk_id, branch_ranks in sorted(
            ranks_by_chunk.items(),
            key=lambda item: (min(item[1].values()), item[0]),
        )
        if len(branch_ranks) >= 2
    ]

    vector_only = [
        existing_entry(chunk_id)
        for chunk_id, branch_ranks in sorted(
            ranks_by_chunk.items(),
            key=lambda item: (item[1].get("vector", 10_000), item[0]),
        )
        if set(branch_ranks) == {"vector"}
    ]

    lexical_only = [
        existing_entry(chunk_id)
        for chunk_id, branch_ranks in sorted(
            ranks_by_chunk.items(),
            key=lambda item: (item[1].get("lexical", 10_000), item[0]),
        )
        if set(branch_ranks) == {"lexical"}
    ]

    hybrid_rescued = [
        existing_entry(entry.chunk_id)
        for entry in final
        if entry.rank <= rescue_rank_threshold
        and len(ranks_by_chunk.get(entry.chunk_id, {})) == 1
    ]

    big_movers = []
    for chunk_id, final_rank in final_ranks.items():
        branch_ranks = ranks_by_chunk.get(chunk_id)
        if not branch_ranks:
            continue
        best_branch_rank = min(branch_ranks.values())
        delta = abs(best_branch_rank - final_rank)
        if delta >= big_mover_threshold:
            big_movers.append(
                RankingMover(
                    chunk_id=chunk_id,
                    document_id=metadata[chunk_id].document_id,
                    from_rank=best_branch_rank,
                    to_rank=final_rank,
                    delta=delta,
                )
            )
    big_movers.sort(key=lambda mover: (-mover.delta, mover.chunk_id))

    dropped_by_threshold = [
        existing_entry(chunk_id)
        for chunk_id in threshold_drops
        if chunk_id in metadata
    ]
    dropped_by_rerank = [
        existing_entry(chunk_id)
        for chunk_id in (rerank_drops or [])
        if chunk_id in metadata
    ]

    return RankingDiff(
        common=common,
        vector_only=vector_only,
        lexical_only=lexical_only,
        hybrid_rescued=hybrid_rescued,
        big_movers=big_movers,
        dropped_by_threshold=dropped_by_threshold,
        dropped_by_rerank=dropped_by_rerank,
    )


def build_explanation(
    entry: BranchResultEntry,
    *,
    branches: BranchRankings,
    diff: RankingDiff | None = None,
    threshold: float | None = None,
) -> ResultExplanation:
    """Build a deterministic explanation from actual branch evidence."""

    branch_entries = _entries_by_branch(branches, entry.chunk_id)
    vector_entry = branch_entries.get("vector")
    lexical_entry = branch_entries.get("lexical")
    signals: list[str] = []
    summary_parts: list[str] = []

    if vector_entry is not None:
        is_semantic_strong = (
            vector_entry.distance is not None and vector_entry.distance <= 0.4
        ) or vector_entry.score >= 0.7
        semantic_signal = "semantic_strong" if is_semantic_strong else "semantic_weak"
        signals.append(semantic_signal)
        summary_parts.append(
            "strong semantic match"
            if semantic_signal == "semantic_strong"
            else "weaker semantic match"
        )
        if threshold is not None and vector_entry.score < threshold:
            signals.append("below_threshold")
            summary_parts.append("below the configured semantic threshold")

    if lexical_entry is not None:
        signals.append("lexical_exact_match")
        if lexical_entry.matched_terms:
            terms = ", ".join(lexical_entry.matched_terms)
            summary_parts.append(f"exact lexical match on {terms}")
        else:
            summary_parts.append("exact lexical match")

    if len(branch_entries) >= 2:
        signals.append("branch_consensus")
        summary_parts.append("branch consensus")

    rescued_ids = {
        rescued.chunk_id
        for rescued in (diff.hybrid_rescued if diff is not None else [])
    }
    if entry.chunk_id in rescued_ids:
        signals.append("hybrid_rescued")
        summary_parts.append("rescued by hybrid fusion")

    unknown_signals = set(signals) - CONTROLLED_EXPLANATION_SIGNALS
    if unknown_signals:
        raise ValueError(f"unknown explanation signals: {', '.join(sorted(unknown_signals))}")

    if not summary_parts:
        return ResultExplanation(
            summary="hybrid fused result without branch-specific evidence.",
            signals=[],
        )

    return ResultExplanation(
        summary=f"{'; '.join(summary_parts)}.",
        signals=signals,
    )
