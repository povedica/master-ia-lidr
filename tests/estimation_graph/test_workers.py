"""Worker partial updates and least-privilege construction (feature-067)."""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from app.services.estimation_graph.agents.budget_searcher import build_budget_searcher
from app.services.estimation_graph.agents.requirements_extractor import (
    build_requirements_extractor,
)


@pytest.mark.asyncio
async def test_requirements_extractor_returns_validated_partial_update() -> None:
    async def fake_complete(**kwargs: Any) -> Any:
        from app.services.estimation_graph.schemas import (
            ExtractedRequirement,
            ExtractedRequirements,
        )

        return ExtractedRequirements(
            requirements=[
                ExtractedRequirement(id="req-1", text="Build REST API", category="backend"),
                ExtractedRequirement(id="req-2", text="Mobile app", category="frontend"),
            ]
        )

    worker = build_requirements_extractor(complete_fn=fake_complete)
    update = await worker({"transcript": "x" * 120, "estimation_id": "e1"})

    assert [row["id"] for row in update["requirements"]] == ["req-1", "req-2"]
    assert update["completed_workers"] == ["requirements_extractor"]
    contribution = update["agent_contributions"][0]
    assert contribution["worker"] == "requirements_extractor"
    assert contribution.get("tool") in (None, "")


@pytest.mark.asyncio
async def test_requirements_extractor_rejects_empty_extraction() -> None:
    async def fake_complete(**kwargs: Any) -> Any:
        from app.services.estimation_graph.schemas import ExtractedRequirements

        return ExtractedRequirements(requirements=[])

    worker = build_requirements_extractor(complete_fn=fake_complete)
    update = await worker({"transcript": "x" * 120})
    assert "requirements" not in update or not update.get("requirements")
    assert update["errors"]
    assert update["completed_workers"] == ["requirements_extractor"]


def test_requirements_extractor_has_no_business_tool_parameter() -> None:
    sig = inspect.signature(build_requirements_extractor)
    assert "search_budgets_fn" not in sig.parameters
    assert "calculate_estimate_fn" not in sig.parameters
    assert "validate_estimate_fn" not in sig.parameters


@pytest.mark.asyncio
async def test_budget_searcher_accumulates_matches_via_search_only() -> None:
    calls: list[dict[str, Any]] = []

    async def fake_search(raw_args: dict[str, Any], *, backend: Any = None) -> dict[str, Any]:
        calls.append(raw_args)
        return {
            "items": [
                {
                    "id": "b-1",
                    "estimated_hours": 80.0,
                    "distance": 0.12,
                    "sector": "logistics",
                }
            ],
            "count": 1,
            "summary": "1 item",
        }

    worker = build_budget_searcher(search_budgets_fn=fake_search)
    update = await worker(
        {
            "requirements": [
                {"id": "req-1", "text": "Build REST API", "category": "backend"},
            ]
        }
    )

    assert calls and "REST API" in calls[0]["query"] or calls[0]["query"]
    assert update["search_attempted"] is True
    assert update["completed_workers"] == ["budget_searcher"]
    assert update["budget_matches"][0]["requirement_id"] == "req-1"
    assert update["budget_matches"][0]["reference_budget_id"] == "b-1"
    assert update["budget_matches"][0]["amount"] == 80.0
    assert update["agent_contributions"][0]["tool"] == "search_budgets"


@pytest.mark.asyncio
async def test_budget_searcher_records_no_match_outcome() -> None:
    async def fake_search(raw_args: dict[str, Any], *, backend: Any = None) -> dict[str, Any]:
        return {"items": [], "count": 0, "summary": "none"}

    worker = build_budget_searcher(search_budgets_fn=fake_search)
    update = await worker(
        {
            "requirements": [
                {"id": "req-x", "text": "Quantum teleportation dashboard", "category": "r&d"},
            ]
        }
    )
    assert update["search_attempted"] is True
    match = update["budget_matches"][0]
    assert match["requirement_id"] == "req-x"
    assert match["reference_budget_id"] is None
    assert match["no_match"] is True


def test_budget_searcher_cannot_be_built_with_calc_or_validate() -> None:
    sig = inspect.signature(build_budget_searcher)
    assert list(sig.parameters) == ["search_budgets_fn", "backend"]
