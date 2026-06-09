"""Shared milestone fixture contract tests (feature-035, step 1)."""

from __future__ import annotations

import json
from pathlib import Path

from app.embedding_pipeline.schemas import Budget, IngestRequest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_BUDGETS_PATH = FIXTURES_DIR / "sample_budgets.json"
BUDGET_FILES_DIR = FIXTURES_DIR / "budget_files"


def test_sample_chunk_id_uses_double_colon_separator() -> None:
    from tests.embedding_pipeline.conftest import SAMPLE_CHUNK

    assert "::" in SAMPLE_CHUNK["chunk_id"]
    assert SAMPLE_CHUNK["chunk_id"] == "BUD-2024-014::AUTH-001"


def test_sample_budgets_fixture_is_valid_ingest_request() -> None:
    payload = json.loads(SAMPLE_BUDGETS_PATH.read_text(encoding="utf-8"))
    request = IngestRequest.model_validate(payload)
    assert len(request.budgets) >= 2


def test_sample_budgets_fixture_has_required_component_counts() -> None:
    payload = json.loads(SAMPLE_BUDGETS_PATH.read_text(encoding="utf-8"))
    budgets = payload["budgets"]
    total_components = sum(len(b["components"]) for b in budgets)
    multi_component_budgets = [b for b in budgets if len(b["components"]) >= 2]
    zero_component_budgets = [b for b in budgets if len(b["components"]) == 0]

    assert total_components >= 3
    assert len(multi_component_budgets) >= 1
    assert len(zero_component_budgets) >= 1


def test_budget_files_directory_has_json_files() -> None:
    json_files = sorted(BUDGET_FILES_DIR.glob("*.json"))
    assert len(json_files) >= 2


def test_each_budget_file_parses_as_budget() -> None:
    for path in sorted(BUDGET_FILES_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        budget = Budget.model_validate(payload)
        assert budget.budget_id
