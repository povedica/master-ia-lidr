"""Unit tests for deterministic CAG stress metrics."""

from __future__ import annotations

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[1]
_tests_dir = _repo_root / "tests"
sys.path[:] = [str(_repo_root)] + [
    entry for entry in sys.path if entry not in {"", str(_repo_root), str(_tests_dir)}
]
for _name in list(sys.modules):
    if _name == "evals" or _name.startswith("evals."):
        _module_file = getattr(sys.modules[_name], "__file__", "") or ""
        if f"{_tests_dir}/evals" in _module_file.replace("\\", "/"):
            del sys.modules[_name]

from evals.stress.metrics import CostBudgetMetric, LatencyBudgetMetric, MemoryDriftMetric


def test_latency_budget_metric_passes_within_budget() -> None:
    result = LatencyBudgetMetric(budget_ms=4000).evaluate({"latency_ms": 2500})
    assert result.passed is True
    assert result.score == 1.0


def test_latency_budget_metric_fails_above_budget() -> None:
    result = LatencyBudgetMetric(budget_ms=4000).evaluate({"latency_ms": 4500})
    assert result.passed is False
    assert result.score == 0.0


def test_cost_budget_metric_passes_within_budget() -> None:
    result = CostBudgetMetric(budget_usd=0.05).evaluate({"cost_usd": 0.02})
    assert result.passed is True
    assert result.score == 1.0


def test_cost_budget_metric_fails_above_budget() -> None:
    result = CostBudgetMetric(budget_usd=0.05).evaluate({"cost_usd": 0.08})
    assert result.passed is False
    assert result.score == 0.0


def test_memory_drift_metric_passes_when_fact_in_summary() -> None:
    snapshot = {
        "project_metadata": {"agreed_scope": "Scope for Nimbus includes auth."},
        "last_derived_metadata": {"summary": "Nimbus platform summary"},
    }
    result = MemoryDriftMetric("nimbus platform summary").evaluate(snapshot)
    assert result.passed is True


def test_memory_drift_metric_fails_when_fact_missing() -> None:
    snapshot = {
        "project_metadata": {"agreed_scope": "Unrelated scope"},
        "last_derived_metadata": {"summary": "Other project"},
    }
    result = MemoryDriftMetric("budget locked: 30000 EUR").evaluate(snapshot)
    assert result.passed is False


def test_memory_drift_metric_is_case_insensitive_and_handles_missing_fields() -> None:
    snapshot = {"project_metadata": {}, "last_derived_metadata": None}
    result = MemoryDriftMetric("STACK INCLUDES FLUTTER", where=["metadata"]).evaluate(snapshot)
    assert result.passed is False
    assert result.details["matched_locations"] == []
