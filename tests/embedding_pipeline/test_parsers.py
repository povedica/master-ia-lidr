"""Unit tests for budget parsers (feature-035)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.embedding_pipeline.parsers.budget_json import BudgetParseError, parse_budget_file
from app.embedding_pipeline.parsers.registry import get_parser
from app.embedding_pipeline.schemas import Budget

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "budget_files"


def test_parse_budget_file_returns_valid_budget() -> None:
    path = FIXTURES_DIR / "bud-2024-014.json"
    budget = parse_budget_file(path)
    assert isinstance(budget, Budget)
    assert budget.budget_id == "BUD-2024-014"
    assert len(budget.components) == 1


def test_parse_budget_file_invalid_json_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(BudgetParseError, match=str(bad)):
        parse_budget_file(bad)


def test_parse_budget_file_invalid_schema_raises(tmp_path: Path) -> None:
    bad = tmp_path / "schema.json"
    bad.write_text(json.dumps({"budget_id": "only-id"}), encoding="utf-8")
    with pytest.raises(BudgetParseError, match=str(bad)):
        parse_budget_file(bad)


def test_registry_returns_json_parser() -> None:
    parser = get_parser("json")
    budget = parser(FIXTURES_DIR / "bud-2024-099.json")
    assert budget.budget_id == "BUD-2024-099"
    assert len(budget.components) == 2
