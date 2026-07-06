"""Tests for RAGAS generation eval gate/monitor helpers (feature-055)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.embedding_pipeline.generation_eval import (
    BaselineParseError,
    GenerationBaseline,
    QueryGenerationMetrics,
    evaluate_gate,
    gate_exit_code,
    load_baseline,
    render_gate_summary,
    render_monitor_summary,
    summarize_generation_metrics,
)

VALID_BASELINE_TEXT = """---
tolerance: 0.05
metrics:
  faithfulness: 0.60
  answer_relevancy: null
  context_precision: 0.86
  context_recall: 0.14
---

# RAGAS Generation Baseline

Seeded from a fixture run for gate unit tests.
"""


def _write_baseline(tmp_path: Path, text: str = VALID_BASELINE_TEXT) -> Path:
    path = tmp_path / "RAGAS_BASELINE.md"
    path.write_text(text, encoding="utf-8")
    return path


def _metrics(faithfulness: float, answer_relevancy: float | None = None) -> object:
    import math

    return summarize_generation_metrics(
        (
            QueryGenerationMetrics(
                "q1",
                faithfulness,
                answer_relevancy if answer_relevancy is not None else math.nan,
                0.9,
                0.5,
            ),
        )
    )


class TestLoadBaseline:
    def test_load_baseline_parses_front_matter(self, tmp_path: Path) -> None:
        baseline = load_baseline(_write_baseline(tmp_path))

        assert baseline == GenerationBaseline(
            tolerance=0.05,
            mean_faithfulness=0.60,
            mean_answer_relevancy=None,
            mean_context_precision=0.86,
            mean_context_recall=0.14,
        )

    def test_load_baseline_missing_file_raises_clear_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist.md"

        with pytest.raises(BaselineParseError, match="not found"):
            load_baseline(missing)

    def test_load_baseline_missing_front_matter_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "no-front-matter.md"
        path.write_text("# Just a heading\n", encoding="utf-8")

        with pytest.raises(BaselineParseError, match="front matter"):
            load_baseline(path)

    def test_load_baseline_missing_metrics_mapping_raises(self, tmp_path: Path) -> None:
        path = _write_baseline(
            tmp_path,
            text="---\ntolerance: 0.05\n---\n\n# No metrics key\n",
        )

        with pytest.raises(BaselineParseError, match="metrics"):
            load_baseline(path)

    def test_load_baseline_defaults_tolerance_when_absent(self, tmp_path: Path) -> None:
        path = _write_baseline(
            tmp_path,
            text=(
                "---\nmetrics:\n  faithfulness: 0.6\n  answer_relevancy: null\n"
                "  context_precision: 0.8\n  context_recall: 0.1\n---\n\n# Baseline\n"
            ),
        )

        baseline = load_baseline(path)

        assert baseline.tolerance == pytest.approx(0.05)


class TestEvaluateGate:
    def test_gate_passes_when_current_meets_baseline(self, tmp_path: Path) -> None:
        baseline = load_baseline(_write_baseline(tmp_path))
        metrics = _metrics(faithfulness=0.60)

        result = evaluate_gate(metrics, baseline)

        assert result.passed is True
        assert gate_exit_code(result) == 0

    def test_gate_passes_within_tolerance_band(self, tmp_path: Path) -> None:
        baseline = load_baseline(_write_baseline(tmp_path))
        # baseline 0.60, tolerance 0.05 -> 0.56 still passes.
        metrics = _metrics(faithfulness=0.56)

        result = evaluate_gate(metrics, baseline)

        assert result.passed is True
        assert gate_exit_code(result) == 0

    def test_gate_fails_below_tolerance_band(self, tmp_path: Path) -> None:
        baseline = load_baseline(_write_baseline(tmp_path))
        # baseline 0.60, tolerance 0.05 -> threshold 0.55; 0.40 regresses.
        metrics = _metrics(faithfulness=0.40)

        result = evaluate_gate(metrics, baseline)

        assert result.passed is False
        assert gate_exit_code(result) == 1
        failing = [c for c in result.comparisons if not c.passed]
        assert failing and failing[0].name == "faithfulness"

    def test_gate_skips_non_finite_answer_relevancy(self, tmp_path: Path) -> None:
        baseline = load_baseline(_write_baseline(tmp_path))
        metrics = _metrics(faithfulness=0.60, answer_relevancy=None)

        result = evaluate_gate(metrics, baseline)

        relevancy = next(c for c in result.comparisons if c.name == "answer_relevancy")
        assert relevancy.passed is True
        assert "skipped" in relevancy.reason

    def test_gate_tolerance_override_widens_pass_band(self, tmp_path: Path) -> None:
        baseline = load_baseline(_write_baseline(tmp_path))
        metrics = _metrics(faithfulness=0.40)

        result = evaluate_gate(metrics, baseline, tolerance=0.25)

        assert result.passed is True
        assert result.tolerance == pytest.approx(0.25)


class TestRenderSummaries:
    def test_render_gate_summary_reports_pass(self, tmp_path: Path) -> None:
        baseline = load_baseline(_write_baseline(tmp_path))
        metrics = _metrics(faithfulness=0.60)

        summary = render_gate_summary(evaluate_gate(metrics, baseline))

        assert "PASS" in summary
        assert "faithfulness" in summary

    def test_render_gate_summary_reports_regression(self, tmp_path: Path) -> None:
        baseline = load_baseline(_write_baseline(tmp_path))
        metrics = _metrics(faithfulness=0.10)

        summary = render_gate_summary(evaluate_gate(metrics, baseline))

        assert "REGRESSION" in summary

    def test_render_monitor_summary_includes_faithfulness_and_relevancy(self) -> None:
        metrics = _metrics(faithfulness=0.6, answer_relevancy=0.7)

        summary = render_monitor_summary(metrics)

        assert "faithfulness=0.600" in summary
        assert "answer_relevancy=0.700" in summary

    def test_render_monitor_summary_uses_na_for_non_finite(self) -> None:
        metrics = _metrics(faithfulness=0.6, answer_relevancy=None)

        summary = render_monitor_summary(metrics)

        assert "answer_relevancy=n/a" in summary
