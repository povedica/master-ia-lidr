"""Evaluation helpers for production retrieval modes (feature-050)."""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.retrieval_service import RetrievalMode

REQUIRED_ALEMBIC_REVISION = "0004"


class _RerankerPreflight(Protocol):
    is_noop: bool


class _SettingsPreflight(Protocol):
    database_url: str
    retrieval_rerank_enabled: bool


@dataclass(frozen=True)
class CorpusSnapshot:
    chunk_count: int
    chunks_with_embedding: int
    chunks_with_content_tsv: int
    chunks_with_budget_id: int
    distinct_budget_ids: frozenset[str]


@dataclass(frozen=True)
class EvaluationPreflightResult:
    ok: bool
    errors: tuple[str, ...]
    corpus: CorpusSnapshot | None = None
    alembic_revision: str | None = None


@dataclass(frozen=True)
class GoldenQuery:
    id: str
    query: str
    relevant_budget_ids: frozenset[str]
    notes: str = ""


@dataclass(frozen=True)
class QueryModeResult:
    query_id: str
    mode: RetrievalMode
    precision_at_5: float
    latency_ms_samples: tuple[float, ...]
    retrieved_budget_ids: tuple[str, ...]
    hit_budget_ids: tuple[str, ...]


@dataclass(frozen=True)
class ModeMetrics:
    mode: RetrievalMode
    precision_at_5: float
    latency_ms_p50: float
    latency_ms_p95: float
    latency_ms_mean: float
    per_query: tuple[QueryModeResult, ...]


def load_golden_set(path: Path) -> list[GoldenQuery]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    queries = payload.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("golden set must contain a non-empty queries list")
    golden: list[GoldenQuery] = []
    for entry in queries:
        if not isinstance(entry, dict):
            raise ValueError("each golden query must be an object")
        query_id = str(entry.get("id", "")).strip()
        query = str(entry.get("query", "")).strip()
        labels = entry.get("relevant_budget_ids")
        if not query_id or not query or not isinstance(labels, list) or not labels:
            raise ValueError(f"invalid golden query entry: {entry!r}")
        golden.append(
            GoldenQuery(
                id=query_id,
                query=query,
                relevant_budget_ids=frozenset(str(label) for label in labels),
                notes=str(entry.get("notes", "")),
            )
        )
    return golden


async def fetch_alembic_revision(session: AsyncSession) -> str | None:
    result = await session.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
    row = result.first()
    if row is None:
        return None
    return str(row[0])


async def fetch_corpus_snapshot(session: AsyncSession) -> CorpusSnapshot:
    counts_result = await session.execute(
        text(
            """
            SELECT
                COUNT(*) AS chunk_count,
                COUNT(embedding) AS chunks_with_embedding,
                COUNT(content_tsv) AS chunks_with_content_tsv,
                COUNT(*) FILTER (
                    WHERE metadata ? 'budget_id'
                    AND NULLIF(metadata->>'budget_id', '') IS NOT NULL
                ) AS chunks_with_budget_id
            FROM chunks
            """
        )
    )
    counts = counts_result.one()
    budget_ids_result = await session.execute(
        text(
            """
            SELECT DISTINCT metadata->>'budget_id' AS budget_id
            FROM chunks
            WHERE metadata ? 'budget_id'
              AND NULLIF(metadata->>'budget_id', '') IS NOT NULL
            """
        )
    )
    distinct_budget_ids = frozenset(
        str(row.budget_id)
        for row in budget_ids_result
        if row.budget_id is not None
    )
    return CorpusSnapshot(
        chunk_count=int(counts.chunk_count),
        chunks_with_embedding=int(counts.chunks_with_embedding),
        chunks_with_content_tsv=int(counts.chunks_with_content_tsv),
        chunks_with_budget_id=int(counts.chunks_with_budget_id),
        distinct_budget_ids=distinct_budget_ids,
    )


def validate_golden_set_corpus_coverage(
    golden_queries: list[GoldenQuery],
    corpus_budget_ids: frozenset[str],
) -> list[str]:
    errors: list[str] = []
    for golden in golden_queries:
        missing = sorted(
            budget_id
            for budget_id in golden.relevant_budget_ids
            if budget_id not in corpus_budget_ids
        )
        if missing:
            errors.append(
                f"Golden query {golden.id}: labels not in corpus: {', '.join(missing)}"
            )
    return errors


def validate_evaluation_preflight(
    *,
    settings: _SettingsPreflight,
    reranker: _RerankerPreflight,
    corpus: CorpusSnapshot | None,
    alembic_revision: str | None,
    golden_queries: list[GoldenQuery],
) -> EvaluationPreflightResult:
    errors: list[str] = []
    if not settings.database_url.strip():
        errors.append("DATABASE_URL is required for retrieval evaluation.")
    if alembic_revision != REQUIRED_ALEMBIC_REVISION:
        errors.append(
            f"Alembic revision must be {REQUIRED_ALEMBIC_REVISION} "
            f"(Spanish content_tsv migration); got {alembic_revision!r}."
        )
    if corpus is None or corpus.chunk_count == 0:
        errors.append("Corpus is empty; ingest budget chunks before evaluation.")
    elif corpus.chunks_with_embedding < corpus.chunk_count:
        errors.append("Some chunks lack embeddings.")
    elif corpus.chunks_with_content_tsv < corpus.chunk_count:
        errors.append("Some chunks lack generated content_tsv.")
    elif corpus.chunks_with_budget_id < corpus.chunk_count:
        errors.append("Some chunks lack metadata.budget_id.")
    if not settings.retrieval_rerank_enabled:
        errors.append(
            "RETRIEVAL_RERANK_ENABLED must be true so modes C/D use a real reranker."
        )
    if reranker.is_noop:
        errors.append(
            "Reranker is no-op; set RETRIEVAL_RERANK_MODEL to a cross-encoder model id."
        )
    if corpus is not None and corpus.distinct_budget_ids:
        errors.extend(
            validate_golden_set_corpus_coverage(
                golden_queries,
                corpus.distinct_budget_ids,
            )
        )
    return EvaluationPreflightResult(
        ok=not errors,
        errors=tuple(errors),
        corpus=corpus,
        alembic_revision=alembic_revision,
    )


def precision_at_5(
    retrieved_budget_ids: list[str],
    relevant_budget_ids: frozenset[str],
    *,
    top_k: int = 5,
) -> float:
    unique_budgets: list[str] = []
    for budget_id in retrieved_budget_ids:
        if budget_id and budget_id not in unique_budgets:
            unique_budgets.append(budget_id)
        if len(unique_budgets) >= top_k:
            break
    if not unique_budgets:
        return 0.0
    hits = sum(1 for budget_id in unique_budgets if budget_id in relevant_budget_ids)
    return hits / top_k


def aggregate_latency_ms(
    samples_ms: list[float],
    *,
    exclude_first: bool = True,
) -> tuple[float, float, float]:
    usable = samples_ms[1:] if exclude_first and len(samples_ms) > 1 else list(samples_ms)
    if not usable:
        usable = list(samples_ms)
    if not usable:
        return 0.0, 0.0, 0.0
    if len(usable) == 1:
        value = usable[0]
        return value, value, value
    ordered = sorted(usable)
    p50 = statistics.median(ordered)
    p95_index = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return p50, ordered[p95_index], statistics.mean(ordered)


def summarize_mode_metrics(results: list[QueryModeResult]) -> ModeMetrics:
    if not results:
        raise ValueError("results must not be empty")
    mode = results[0].mode
    per_query_latency: list[float] = []
    for item in results:
        p50, _, _ = aggregate_latency_ms(list(item.latency_ms_samples))
        per_query_latency.append(p50)
    precision_values = [item.precision_at_5 for item in results]
    all_latencies = [value for item in results for value in item.latency_ms_samples]
    p50, p95, mean = aggregate_latency_ms(all_latencies)
    return ModeMetrics(
        mode=mode,
        precision_at_5=statistics.mean(precision_values),
        latency_ms_p50=p50,
        latency_ms_p95=p95,
        latency_ms_mean=mean,
        per_query=tuple(results),
    )


def render_comparison_markdown(
    metrics: list[ModeMetrics],
    *,
    baseline_mode: RetrievalMode = RetrievalMode.A,
) -> str:
    baseline = next(item for item in metrics if item.mode == baseline_mode)
    lines = [
        "# Retrieval mode comparison",
        "",
        "| Mode | Precision@5 | Latency p50 (ms) | Latency p95 (ms) | Latency mean (ms) | Δ Precision@5 vs A | Δ Latency p50 vs A |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in sorted(metrics, key=lambda value: value.mode.value):
        lines.append(
            "| {mode} | {precision:.3f} | {p50:.1f} | {p95:.1f} | {mean:.1f} | {delta_precision:+.3f} | {delta_p50:+.1f} |".format(
                mode=item.mode.value,
                precision=item.precision_at_5,
                p50=item.latency_ms_p50,
                p95=item.latency_ms_p95,
                mean=item.latency_ms_mean,
                delta_precision=item.precision_at_5 - baseline.precision_at_5,
                delta_p50=item.latency_ms_p50 - baseline.latency_ms_p50,
            )
        )
    return "\n".join(lines) + "\n"


def render_recommendation_markdown(metrics: list[ModeMetrics]) -> str:
    best = max(metrics, key=lambda item: (item.precision_at_5, -item.latency_ms_p50))
    baseline = next(item for item in metrics if item.mode == RetrievalMode.A)
    mode_by_value = {item.mode: item for item in metrics}
    vector_rerank = mode_by_value.get(RetrievalMode.C)
    hybrid_rerank = mode_by_value.get(RetrievalMode.D)
    lines = [
        "# Retrieval recommendation",
        "",
        f"Recommended production candidate: **Mode {best.mode.value}**.",
        "",
        "Rationale:",
        f"- Highest mean precision@5 ({best.precision_at_5:.3f}) in this run.",
        f"- Latency p50 {best.latency_ms_p50:.1f} ms vs baseline mode A ({baseline.latency_ms_p50:.1f} ms).",
        "- Golden set size is small (5 queries); treat deltas as directional, not statistically significant.",
        "",
        "## Reranking trade-off",
    ]
    if vector_rerank is not None:
        vector_only = mode_by_value[RetrievalMode.A]
        delta_precision = vector_rerank.precision_at_5 - vector_only.precision_at_5
        delta_latency = vector_rerank.latency_ms_p50 - vector_only.latency_ms_p50
        lines.extend(
            [
                f"- Vector + rerank (C) vs vector-only (A): "
                f"Δ precision@5 {delta_precision:+.3f}, Δ latency p50 {delta_latency:+.1f} ms.",
            ]
        )
    if hybrid_rerank is not None:
        hybrid_only = mode_by_value[RetrievalMode.B]
        delta_precision = hybrid_rerank.precision_at_5 - hybrid_only.precision_at_5
        delta_latency = hybrid_rerank.latency_ms_p50 - hybrid_only.latency_ms_p50
        lines.extend(
            [
                f"- Hybrid + rerank (D) vs hybrid-only (B): "
                f"Δ precision@5 {delta_precision:+.3f}, Δ latency p50 {delta_latency:+.1f} ms.",
            ]
        )
    rerank_modes = [item for item in metrics if item.mode in {RetrievalMode.C, RetrievalMode.D}]
    if rerank_modes:
        best_rerank = max(rerank_modes, key=lambda item: item.precision_at_5)
        non_rerank_pair = {
            RetrievalMode.C: RetrievalMode.A,
            RetrievalMode.D: RetrievalMode.B,
        }[best_rerank.mode]
        paired = mode_by_value[non_rerank_pair]
        precision_gain = best_rerank.precision_at_5 - paired.precision_at_5
        latency_cost = best_rerank.latency_ms_p50 - paired.latency_ms_p50
        if precision_gain > 0 and latency_cost > 0:
            verdict = (
                f"Reranking (mode {best_rerank.mode.value}) improves precision@5 by "
                f"{precision_gain:.3f} at a p50 latency cost of {latency_cost:.1f} ms "
                "for this corpus and golden set."
            )
        elif precision_gain <= 0:
            verdict = (
                "Reranking did not improve mean precision@5 over its non-rerank counterpart "
                "in this run; latency cost is not justified on this evidence alone."
            )
        else:
            verdict = (
                f"Reranking (mode {best_rerank.mode.value}) improved precision@5 without "
                f"a measured p50 latency increase in this local run."
            )
        lines.extend(["", verdict, ""])
    return "\n".join(lines)


def detect_noop_rerank_warning(
    *,
    mode: RetrievalMode,
    rerank_is_noop: bool,
) -> str | None:
    if mode in {RetrievalMode.C, RetrievalMode.D} and rerank_is_noop:
        return (
            f"Mode {mode.value} used a no-op reranker; results are not valid for rerank comparison."
        )
    return None


def metrics_to_json(metrics: list[ModeMetrics]) -> dict[str, Any]:
    return {
        "modes": [
            {
                "mode": item.mode.value,
                "precision_at_5": item.precision_at_5,
                "latency_ms_p50": item.latency_ms_p50,
                "latency_ms_p95": item.latency_ms_p95,
                "latency_ms_mean": item.latency_ms_mean,
                "per_query": [
                    {
                        "query_id": query.query_id,
                        "precision_at_5": query.precision_at_5,
                        "latency_ms_samples": list(query.latency_ms_samples),
                        "retrieved_budget_ids": list(query.retrieved_budget_ids),
                        "hit_budget_ids": list(query.hit_budget_ids),
                    }
                    for query in item.per_query
                ],
            }
            for item in metrics
        ]
    }
