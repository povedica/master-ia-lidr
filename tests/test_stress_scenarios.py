"""Unit tests for deterministic stress scenario generators."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

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

from evals.stress.scenarios import build_scenario, list_supported_turn_counts


@pytest.mark.parametrize("name", ["growing", "pivot", "contradiction"])
@pytest.mark.parametrize("n_turns", [1, 3, 6, 10, 20])
def test_build_scenario_produces_expected_turn_count(name: str, n_turns: int) -> None:
    scenario = build_scenario(name, n_turns)
    assert scenario.scenario_name == name
    assert len(scenario.turns) == n_turns
    assert [turn.turn_index for turn in scenario.turns] == list(range(1, n_turns + 1))
    for turn in scenario.turns:
        assert len(turn.transcript) >= 80
        assert turn.fact_to_remember


def test_build_scenario_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="unsupported scenario"):
        build_scenario("burst", 3)


def test_list_supported_turn_counts_matches_exercise_set() -> None:
    assert list_supported_turn_counts() == (1, 3, 6, 10, 20)
