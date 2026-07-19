"""Worker partial updates and least-privilege construction (feature-067)."""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from app.services.estimation_graph.agents.budget_searcher import build_budget_searcher
from app.services.estimation_graph.agents.coherence_validator import (
    build_coherence_validator,
)
from app.services.estimation_graph.agents.estimate_generator import (
    build_estimate_generator,
)
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


@pytest.mark.asyncio
async def test_estimate_generator_maps_matches_without_inventing_references() -> None:
    captured: dict[str, Any] = {}

    def fake_calculate(raw_args: dict[str, Any]) -> dict[str, Any]:
        captured["args"] = raw_args
        return {
            "components": [
                {
                    "name": "API",
                    "reference_count": 1,
                    "estimated_hours": 92.0,
                    "unbudgeted": False,
                },
                {
                    "name": "Quantum UI",
                    "reference_count": 0,
                    "estimated_hours": 0.0,
                    "unbudgeted": True,
                },
            ],
            "total_hours": 92.0,
            "contingency_factor": 0.15,
            "summary": "total=92.0h",
        }

    worker = build_estimate_generator(calculate_estimate_fn=fake_calculate)
    update = await worker(
        {
            "requirements": [
                {"id": "req-1", "text": "API", "category": "backend"},
                {"id": "req-2", "text": "Quantum UI", "category": "frontend"},
            ],
            "budget_matches": [
                {
                    "requirement_id": "req-1",
                    "reference_budget_id": "b1",
                    "amount": 80.0,
                    "distance": 0.1,
                    "component": "API",
                    "no_match": False,
                },
                {
                    "requirement_id": "req-2",
                    "reference_budget_id": None,
                    "amount": 0.0,
                    "distance": 1.0,
                    "component": "Quantum UI",
                    "no_match": True,
                },
            ],
        }
    )

    components = captured["args"]["components"]
    by_name = {row["name"]: row["reference_amounts"] for row in components}
    assert by_name["API"] == [80.0]
    assert by_name["Quantum UI"] == []
    assert update["estimate"]["total_hours"] == 92.0
    assert update["completed_workers"] == ["estimate_generator"]
    assert update["agent_contributions"][0]["tool"] == "calculate_estimate"


@pytest.mark.asyncio
async def test_estimate_generator_preserves_unbudgeted_components() -> None:
    def fake_calculate(raw_args: dict[str, Any]) -> dict[str, Any]:
        return {
            "components": [
                {
                    "name": "Unknown",
                    "reference_count": 0,
                    "estimated_hours": 0.0,
                    "unbudgeted": True,
                }
            ],
            "total_hours": 0.0,
            "contingency_factor": 0.15,
            "summary": "total=0.0h",
        }

    worker = build_estimate_generator(calculate_estimate_fn=fake_calculate)
    update = await worker(
        {
            "requirements": [{"id": "req-1", "text": "Unknown", "category": "r&d"}],
            "budget_matches": [
                {
                    "requirement_id": "req-1",
                    "reference_budget_id": None,
                    "no_match": True,
                    "amount": 0.0,
                    "distance": 1.0,
                    "component": "Unknown",
                }
            ],
        }
    )
    assert update["estimate"]["components"][0]["unbudgeted"] is True


def test_estimate_generator_signature_is_calc_only() -> None:
    sig = inspect.signature(build_estimate_generator)
    assert "calculate_estimate_fn" in sig.parameters
    assert "search_budgets_fn" not in sig.parameters
    assert "validate_estimate_fn" not in sig.parameters


@pytest.mark.asyncio
async def test_coherence_validator_derives_confidence_and_review_signals() -> None:
    def fake_validate(raw_args: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": False,
            "issues": ["'Quantum UI' has no historical reference (unbudgeted)."],
            "summary": "1 issue(s) found",
        }

    worker = build_coherence_validator(validate_estimate_fn=fake_validate)
    update = await worker(
        {
            "estimate": {
                "components": [
                    {
                        "name": "API",
                        "estimated_hours": 92.0,
                        "unbudgeted": False,
                        "reference_count": 1,
                    },
                    {
                        "name": "Quantum UI",
                        "estimated_hours": 0.0,
                        "unbudgeted": True,
                        "reference_count": 0,
                    },
                ],
                "total_hours": 92.0,
            },
            "budget_matches": [
                {
                    "requirement_id": "req-1",
                    "reference_budget_id": "b1",
                    "amount": 80.0,
                    "no_match": False,
                    "component": "API",
                    "distance": 0.1,
                },
                {
                    "requirement_id": "req-2",
                    "reference_budget_id": None,
                    "amount": 0.0,
                    "no_match": True,
                    "component": "Quantum UI",
                    "distance": 1.0,
                },
            ],
        }
    )

    validation = update["validation"]
    assert validation["ok"] is False
    assert validation["no_precedent"] is True
    assert 0.0 <= update["confidence"] <= 1.0
    assert update["confidence"] < 0.70
    assert "no relevant historical precedent" in validation["review_reasons"]
    assert update["completed_workers"] == ["coherence_validator"]
    assert update["agent_contributions"][0]["tool"] == "validate_estimate"
    assert update.get("human_adjustment_validated") is not True


@pytest.mark.asyncio
async def test_coherence_validator_marks_adjustment_validated_after_adjust() -> None:
    def fake_validate(raw_args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "issues": [], "summary": "ok"}

    worker = build_coherence_validator(validate_estimate_fn=fake_validate)
    update = await worker(
        {
            "estimate": {
                "components": [
                    {
                        "name": "API",
                        "estimated_hours": 90.0,
                        "unbudgeted": False,
                        "reference_count": 1,
                    }
                ],
                "total_hours": 90.0,
            },
            "budget_matches": [
                {
                    "requirement_id": "req-1",
                    "reference_budget_id": "b1",
                    "amount": 80.0,
                    "no_match": False,
                    "component": "API",
                    "distance": 0.1,
                }
            ],
            "human_resolution": {
                "action": "adjust",
                "adjusted_estimate": {"total_hours": 90.0},
            },
        }
    )
    assert update["human_adjustment_validated"] is True
    assert update["validation"]["ok"] is True


def test_coherence_validator_signature_is_validate_only() -> None:
    sig = inspect.signature(build_coherence_validator)
    assert "validate_estimate_fn" in sig.parameters
    assert "search_budgets_fn" not in sig.parameters
    assert "calculate_estimate_fn" not in sig.parameters
