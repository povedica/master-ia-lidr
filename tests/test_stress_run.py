"""Unit tests for stress runner path helpers."""

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

from evals.stress.run import scenario_artifact_path


def test_scenario_artifact_path_inserts_scenario_before_suffix() -> None:
    assert scenario_artifact_path(Path("evals/stress/results.csv"), "pivot") == Path(
        "evals/stress/results-pivot.csv"
    )
    assert scenario_artifact_path(Path("evals/stress/REPORT.md"), "contradiction") == Path(
        "evals/stress/REPORT-contradiction.md"
    )
