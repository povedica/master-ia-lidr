"""Estimate totals arithmetic (gate-2 editable hours) — no network."""

from __future__ import annotations

from app.services.estimation_graph.agents._common import (
    build_estimate,
    flag_reason,
    recompute_estimate_totals,
)


def _modules(*pairs: tuple[str, int | None]) -> list[dict]:
    return [
        {
            "name": "M",
            "tasks": [{"name": name, "estimated_hours": hours} for name, hours in pairs],
        }
    ]


def test_all_grounded_is_high() -> None:
    assert recompute_estimate_totals(_modules(("A", 40), ("B", 24))) == {
        "total_engineer_hours": 64.0,
        "total_engineer_days": 8,
        "grounded_task_ratio": 1.0,
        "confidence": "high",
    }


def test_mixed_is_medium() -> None:
    totals = recompute_estimate_totals(_modules(("A", 40), ("B", None)))
    assert totals["confidence"] == "medium"
    assert totals["grounded_task_ratio"] == 0.5
    assert totals["total_engineer_hours"] == 40.0
    assert totals["total_engineer_days"] == 5


def test_none_grounded_is_low() -> None:
    assert recompute_estimate_totals(_modules(("A", None), ("B", None))) == {
        "total_engineer_hours": 0.0,
        "total_engineer_days": 0,
        "grounded_task_ratio": 0.0,
        "confidence": "low",
    }


def test_build_estimate_grafts_hours_and_delegates_totals() -> None:
    estimate = build_estimate(
        [
            {
                "name": "M",
                "tasks": [
                    {"name": "A", "description": "a"},
                    {"name": "B", "description": "b"},
                ],
            }
        ],
        [
            {
                "module": "M",
                "task": "A",
                "estimated_hours": 40,
                "has_match": True,
                "reliability": 0.9,
            }
        ],
    )
    assert estimate["total_engineer_hours"] == 40.0
    assert estimate["grounded_task_ratio"] == 0.5
    assert estimate["confidence"] == "medium"
    tasks = estimate["modules"][0]["tasks"]
    assert tasks[0]["estimated_hours"] == 40 and tasks[0]["has_match"] is True
    assert tasks[1]["estimated_hours"] is None and tasks[1]["has_match"] is False


def test_flag_reason_detects_no_match_and_hour_range() -> None:
    assert flag_reason({"has_match": False}) == (
        "no historical analog under the distance threshold"
    )
    assert flag_reason({"has_match": True, "hour_range": {"low": 10, "high": 40}})
    assert flag_reason({"has_match": True, "reliability": 0.9, "hour_range": None}) is None
