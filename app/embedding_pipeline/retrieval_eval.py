"""Evaluation helpers for production retrieval modes (feature-050)."""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.embedding_pipeline.retrieval_service import RetrievalMode


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
    return "\n".join(
        [
            "# Retrieval recommendation",
            "",
            f"Recommended production candidate: **Mode {best.mode.value}**.",
            "",
            "Rationale:",
            f"- Highest mean precision@5 ({best.precision_at_5:.3f}) in this run.",
            f"- Latency p50 {best.latency_ms_p50:.1f} ms vs baseline mode A ({baseline.latency_ms_p50:.1f} ms).",
            "- Golden set size is small (5 queries); treat deltas as directional, not statistically significant.",
            "",
        ]
    )


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
