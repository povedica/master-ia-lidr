"""Tests for retrieval evaluation helpers (feature-050)."""

from __future__ import annotations

import pytest

from app.embedding_pipeline.retrieval_eval import (
    GoldenQuery,
    ModeMetrics,
    QueryModeResult,
    aggregate_latency_ms,
    detect_noop_rerank_warning,
    load_golden_set,
    precision_at_5,
    render_comparison_markdown,
    summarize_mode_metrics,
)
from app.embedding_pipeline.retrieval_service import RetrievalMode


def test_precision_at_5_deduplicates_budget_ids_before_scoring() -> None:
    score = precision_at_5(
        ["BUD-1", "BUD-1", "BUD-2", "BUD-3", "BUD-4", "BUD-5"],
        frozenset({"BUD-1", "BUD-3"}),
    )
    assert score == pytest.approx(0.4)


def test_precision_at_5_handles_empty_results() -> None:
    assert precision_at_5([], frozenset({"BUD-1"})) == 0.0


def test_aggregate_latency_excludes_first_sample_by_default() -> None:
    p50, p95, mean = aggregate_latency_ms([100.0, 10.0, 20.0, 30.0])
    assert p50 == pytest.approx(20.0)
    assert mean == pytest.approx(20.0)
    assert p95 == pytest.approx(30.0)


def test_aggregate_latency_single_sample_edge_case() -> None:
    p50, p95, mean = aggregate_latency_ms([42.0], exclude_first=False)
    assert p50 == p95 == mean == pytest.approx(42.0)


def test_render_comparison_markdown_includes_delta_vs_mode_a() -> None:
    metrics = [
        ModeMetrics(
            mode=RetrievalMode.A,
            precision_at_5=0.2,
            latency_ms_p50=100.0,
            latency_ms_p95=120.0,
            latency_ms_mean=110.0,
            per_query=(),
        ),
        ModeMetrics(
            mode=RetrievalMode.B,
            precision_at_5=0.4,
            latency_ms_p50=130.0,
            latency_ms_p95=150.0,
            latency_ms_mean=140.0,
            per_query=(),
        ),
    ]
    table = render_comparison_markdown(metrics)
    assert "Δ Precision@5 vs A" in table
    assert "| B | 0.400" in table


def test_detect_noop_rerank_warning_for_modes_c_and_d() -> None:
    warning = detect_noop_rerank_warning(mode=RetrievalMode.C, rerank_is_noop=True)
    assert warning is not None
    assert "no-op" in warning.lower()


def test_load_golden_set_from_repo_file() -> None:
    from pathlib import Path

    path = Path("evaluation/retrieval/golden_set.json")
    queries = load_golden_set(path)
    assert len(queries) == 5
    assert isinstance(queries[0], GoldenQuery)


def test_summarize_mode_metrics_averages_precision() -> None:
    results = [
        QueryModeResult(
            query_id="q1",
            mode=RetrievalMode.A,
            precision_at_5=0.4,
            latency_ms_samples=(100.0, 90.0),
            retrieved_budget_ids=("BUD-1",),
            hit_budget_ids=("BUD-1",),
        ),
        QueryModeResult(
            query_id="q2",
            mode=RetrievalMode.A,
            precision_at_5=0.2,
            latency_ms_samples=(110.0, 95.0),
            retrieved_budget_ids=("BUD-2",),
            hit_budget_ids=(),
        ),
    ]
    summary = summarize_mode_metrics(results)
    assert summary.precision_at_5 == pytest.approx(0.3)
