"""Unit tests for stress report generation."""

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

from evals.stress.report import write_report


def test_write_report_generates_tables_and_interpretation(tmp_path: Path) -> None:
    csv_path = tmp_path / "results.csv"
    csv_path.write_text(
        "\n".join(
            [
                "scenario_name,attachment_size_kb,scenario_turn_count,turn_index,latency_ms,tokens_in,cost_usd,cache_hit_kind,metric_memory_drift_score",
                "growing,0,3,1,1200,900,0.01,none,1.0",
                "growing,0,3,2,1800,1200,0.02,none,0.5",
                "growing,0,3,3,2400,1500,0.03,semantic,0.4",
            ]
        ),
        encoding="utf-8",
    )
    report_path = tmp_path / "REPORT.md"
    write_report(csv_path, report_path)
    content = report_path.read_text(encoding="utf-8")
    assert "## Summary" in content
    assert "## Curve 1" in content
    assert "## Curve 2" in content
    assert "## Curve 3" in content
    assert "## Interpretation" in content
    assert "mean memory drift" in content
