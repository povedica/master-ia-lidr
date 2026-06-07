"""Unit tests for golden session YAML loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.evals.loader import GoldenLoaderError, get_case, list_case_files, list_cases, load_case_file
from tests.evals.models import GoldenCategory, GoldenSessionCase


def test_list_case_files_finds_golden_yaml() -> None:
    files = list_case_files()
    assert len(files) >= 6
    assert all(path.suffix == ".yaml" for path in files)


def test_list_cases_loads_all_mandatory_categories() -> None:
    cases = list_cases()
    categories = {case.category for case in cases}
    for required in GoldenCategory:
        assert required in categories, f"missing category: {required.value}"


def test_get_case_returns_known_case() -> None:
    case = get_case("small-single-turn-web")
    assert case.category == GoldenCategory.SMALL


def test_get_case_unknown_raises() -> None:
    with pytest.raises(GoldenLoaderError, match="unknown case_id"):
        get_case("does-not-exist")


def test_load_case_file_rejects_invalid_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("case_id: [unclosed", encoding="utf-8")
    with pytest.raises(GoldenLoaderError, match="invalid YAML"):
        load_case_file(bad)


def test_load_case_file_rejects_invalid_schema(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("case_id: ok\n", encoding="utf-8")
    with pytest.raises(GoldenLoaderError):
        load_case_file(bad)


def test_each_case_has_valid_eval_turn_index() -> None:
    for case in list_cases():
        assert isinstance(case, GoldenSessionCase)
        assert case.eval_turn_index < len(case.turns)
