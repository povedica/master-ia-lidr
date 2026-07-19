"""End-to-end supervisor/worker graph runs, network-free (feature-067)."""

from __future__ import annotations

from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.config import get_settings
from app.services.estimation_graph.build import build_graph
from app.services.estimation_graph.schemas import (
    ExtractedRequirement,
    ExtractedRequirements,
)

TRANSCRIPT = "A" * 200
CONFIG = {"configurable": {"thread_id": "t1"}}


async def _fake_complete(**kwargs: Any) -> ExtractedRequirements:
    return ExtractedRequirements(
        requirements=[
            ExtractedRequirement(id="req-1", text="REST API", category="backend"),
            ExtractedRequirement(id="req-2", text="Mobile app", category="frontend"),
        ]
    )


async def _search_with_matches(raw_args: dict[str, Any], *, backend: Any = None) -> dict[str, Any]:
    del backend
    return {
        "items": [
            {
                "id": f"b-{abs(hash(raw_args['query'])) % 1000}",
                "estimated_hours": 80.0,
                "distance": 0.1,
            }
        ],
        "count": 1,
        "summary": "1 item",
    }


async def _search_no_matches(raw_args: dict[str, Any], *, backend: Any = None) -> dict[str, Any]:
    del raw_args, backend
    return {"items": [], "count": 0, "summary": "none"}


def _calculate(raw_args: dict[str, Any]) -> dict[str, Any]:
    components = []
    total = 0.0
    for component in raw_args["components"]:
        refs = component["reference_amounts"]
        hours = round(float(refs[0]) * 1.15, 1) if refs else 0.0
        total += hours
        components.append(
            {
                "name": component["name"],
                "reference_count": len(refs),
                "estimated_hours": hours,
                "unbudgeted": not refs,
            }
        )
    return {
        "components": components,
        "total_hours": round(total, 1),
        "contingency_factor": 0.15,
        "summary": f"total={round(total, 1)}h",
    }


def _validate_ok(raw_args: dict[str, Any]) -> dict[str, Any]:
    del raw_args
    return {"ok": True, "issues": [], "summary": "estimate passed all guardrails"}


def _validate_unbudgeted(raw_args: dict[str, Any]) -> dict[str, Any]:
    issues = [
        f"{component['name']!r} has no historical reference (unbudgeted)."
        for component in raw_args["components"]
        if not component.get("reference_amounts")
    ]
    return {
        "ok": not issues,
        "issues": issues,
        "summary": "ok" if not issues else f"{len(issues)} issue(s) found",
    }


def _graph(**kwargs: Any):
    return build_graph(MemorySaver(), complete_fn=_fake_complete, **kwargs)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_normal_path_completes_without_interrupt() -> None:
    graph = _graph(
        search_budgets_fn=_search_with_matches,
        calculate_estimate_fn=_calculate,
        validate_estimate_fn=_validate_ok,
        confidence_threshold=0.70,
    )
    result = await graph.ainvoke(
        {"transcript": TRANSCRIPT, "estimation_id": "t1", "status": "running"},
        CONFIG,
    )
    snap = await graph.aget_state(CONFIG)
    assert snap.next == ()
    assert result["status"] == "completed"
    assert result["estimate"]["total_hours"] > 0
    assert result["confidence"] >= 0.70
    assert "requirements_extractor" in result["completed_workers"]
    assert "coherence_validator" in result["completed_workers"]


@pytest.mark.asyncio
async def test_risk_path_pauses_then_approve_completes() -> None:
    graph = _graph(
        search_budgets_fn=_search_no_matches,
        calculate_estimate_fn=_calculate,
        validate_estimate_fn=_validate_unbudgeted,
        confidence_threshold=0.70,
    )
    await graph.ainvoke(
        {"transcript": TRANSCRIPT, "estimation_id": "t1", "status": "running"},
        CONFIG,
    )
    snap = await graph.aget_state(CONFIG)
    assert snap.next == ("human_review",)
    assert snap.interrupts[0].value["gate"] == "estimation_review"
    assert snap.values["status"] == "awaiting_human_review"

    result = await graph.ainvoke(
        Command(resume={"action": "approve", "comment": "accepted"}),
        CONFIG,
    )
    snap = await graph.aget_state(CONFIG)
    assert snap.next == ()
    assert result["status"] == "completed"
    assert result["human_resolution"]["action"] == "approve"


@pytest.mark.asyncio
async def test_adjust_path_revalidates_without_review_loop() -> None:
    graph = _graph(
        search_budgets_fn=_search_no_matches,
        calculate_estimate_fn=_calculate,
        validate_estimate_fn=_validate_unbudgeted,
        confidence_threshold=0.70,
    )
    await graph.ainvoke(
        {"transcript": TRANSCRIPT, "estimation_id": "t1", "status": "running"},
        CONFIG,
    )
    result = await graph.ainvoke(
        Command(
            resume={
                "action": "adjust",
                "adjusted_estimate": {
                    "components": [
                        {
                            "name": "REST API",
                            "estimated_hours": 100.0,
                            "unbudgeted": False,
                            "reference_count": 1,
                        }
                    ],
                    "total_hours": 100.0,
                },
                "comment": "manual fold",
            }
        ),
        CONFIG,
    )
    snap = await graph.aget_state(CONFIG)
    assert snap.next == ()
    assert result["status"] == "completed"
    assert result["human_adjustment_validated"] is True
    assert result["estimate"]["total_hours"] == 100.0


@pytest.mark.asyncio
async def test_reject_path_ends_rejected() -> None:
    graph = _graph(
        search_budgets_fn=_search_no_matches,
        calculate_estimate_fn=_calculate,
        validate_estimate_fn=_validate_unbudgeted,
        confidence_threshold=0.70,
    )
    await graph.ainvoke(
        {"transcript": TRANSCRIPT, "estimation_id": "t1", "status": "running"},
        CONFIG,
    )
    result = await graph.ainvoke(
        Command(resume={"action": "reject", "comment": "insufficient"}),
        CONFIG,
    )
    snap = await graph.aget_state(CONFIG)
    assert snap.next == ()
    assert result["status"] == "rejected"


@pytest.mark.asyncio
async def test_resume_reentry_does_not_duplicate_matches() -> None:
    graph = _graph(
        search_budgets_fn=_search_no_matches,
        calculate_estimate_fn=_calculate,
        validate_estimate_fn=_validate_unbudgeted,
        confidence_threshold=0.70,
    )
    await graph.ainvoke(
        {"transcript": TRANSCRIPT, "estimation_id": "t1", "status": "running"},
        CONFIG,
    )
    snap = await graph.aget_state(CONFIG)
    matches_before = list(snap.values["budget_matches"])
    contributions_before = list(snap.values["agent_contributions"])

    await graph.ainvoke(Command(resume={"action": "approve"}), CONFIG)
    snap = await graph.aget_state(CONFIG)
    assert len(snap.values["budget_matches"]) == len(matches_before)
    # Contributions may grow by human_review / supervisor records only; matches stay stable.
    assert len(snap.values["budget_matches"]) == 2
    assert all(row.get("no_match") for row in snap.values["budget_matches"])
    assert len(snap.values["agent_contributions"]) >= len(contributions_before)
