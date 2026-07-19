"""Smoke checks for Session 12 exercise assets."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SESSION_12_DIR = Path(__file__).resolve().parents[2] / "exercises" / "session-12"
REQUIRED_FILES = (
    "sample_transcript_simple.txt",
    "sample_transcript_complex.txt",
    "reference_retrieval.py",
    "calculate_estimate_skeleton.py",
    "README.md",
)
EXPECTED_STUB_KEYS = {
    "id",
    "content_preview",
    "sector",
    "budget_id",
    "estimated_hours",
    "distance",
}


def _load_stub_module():
    spec = importlib.util.spec_from_file_location(
        "session_12_reference_retrieval",
        SESSION_12_DIR / "reference_retrieval.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_session_12_assets_exist() -> None:
    for name in REQUIRED_FILES:
        assert (SESSION_12_DIR / name).is_file(), f"missing {name}"


def test_search_budgets_stub_returns_expected_shape() -> None:
    stub = _load_stub_module()
    results = stub.search_budgets_stub("oauth jwt authentication backend")
    assert results, "expected at least one stub hit for auth query"
    assert EXPECTED_STUB_KEYS.issubset(results[0].keys())


def test_calculate_estimate_skeleton_runs() -> None:
    spec = importlib.util.spec_from_file_location(
        "session_12_calculate_estimate_skeleton",
        SESSION_12_DIR / "calculate_estimate_skeleton.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.calculate_estimate(
        {
            "components": [
                {"name": "Auth backend", "reference_amounts": [420.0, 380.0]},
            ]
        }
    )
    assert result["total_hours"] > 0
    assert result["components"][0]["unbudgeted"] is False
    assert "summary" in result
