"""Tests for generation golden set loader (FR-13)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.embedding_pipeline.generation_eval import load_generation_golden_set

GOLDEN_PATH = Path("evaluation/generation/golden_set.json")


def test_load_generation_golden_set_returns_five_queries() -> None:
    golden = load_generation_golden_set(GOLDEN_PATH)
    assert len(golden) == 5
    assert {item.id for item in golden} == {
        "q1-oauth-stripe",
        "q2-jwt-api",
        "q3-crm-paraphrase",
        "q4-payments-mobile",
        "q5-data-platform",
    }
    assert all(item.ground_truth.strip() for item in golden)


def test_load_generation_golden_set_rejects_missing_ground_truth(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        '{"queries":[{"id":"q1","question":"test question here","ground_truth":""}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid generation golden query"):
        load_generation_golden_set(path)


def test_load_generation_golden_set_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "dup.json"
    path.write_text(
        """
        {"queries":[
          {"id":"q1","question":"first question text","ground_truth":"answer one"},
          {"id":"q1","question":"second question text","ground_truth":"answer two"}
        ]}
        """,
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_generation_golden_set(path)
