"""Unit tests for Session 13 CLI helpers (feature-066 Step 7)."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.config import get_settings
from app.schemas.rag_task_hours import TaskHoursEstimateView
from app.scripts.run_graph_s13 import (
    GATE_DECISIONS,
    install_stub_hours,
    render_run,
    run_to_completion,
)
from app.services.agentic.agent_schemas import (
    AgentModuleNode,
    AgentStructure,
    AgentTaskNode,
    AgentTrace,
)
from app.services.estimation_graph.build import build_graph
from app.services.estimation_graph.schemas import (
    CommercialProposal,
    ComplexityClassification,
    ReliabilityReport,
)


class _FakeStructured:
    async def __call__(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type,
        model: str,
        settings: object,
    ):
        del system_prompt, user_prompt, model, settings
        if response_model is ComplexityClassification:
            return ComplexityClassification(
                complexity="medium",
                reformulated_transcript="Backend and mobile app.",
                reasoning="two components",
            )
        if response_model is ReliabilityReport:
            return ReliabilityReport(
                overall_confidence="high",
                grounded_task_ratio=1.0,
                weak_points=[],
                summary="ok",
            )
        if response_model is CommercialProposal:
            return CommercialProposal(
                title="Demo",
                executive_summary="Summary",
                scope=["Backend"],
                total_engineer_days=10,
                body_markdown="# Demo\n",
            )
        raise AssertionError(f"unexpected response_model {response_model!r}")


async def _fake_structure(brief, *, client, model, reasoning_effort="medium", persona=None):
    del brief, client, model, reasoning_effort, persona
    struct = AgentStructure(
        modules=[
            AgentModuleNode(
                name="Backend",
                tasks=[AgentTaskNode(name="API", description="REST API")],
            ),
            AgentModuleNode(
                name="Mobile",
                tasks=[AgentTaskNode(name="App", description="iOS/Android")],
            ),
        ],
        confidence="high",
        reasoning="decomposed",
    )
    return struct, AgentTrace()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_gate_decisions_cover_both_interrupts() -> None:
    assert GATE_DECISIONS["structure_review"]["approved"] is True
    assert GATE_DECISIONS["final_review"]["validated"] is True
    assert GATE_DECISIONS["final_review"]["want_proposal"] is True


def test_render_run_includes_structure_estimate_and_proposal() -> None:
    text = render_run(
        {
            "estimation_id": "s13-demo",
            "complexity": "high",
            "status": "validated",
            "structure": {
                "modules": [
                    {"name": "Backend", "tasks": [{"name": "API"}]},
                ]
            },
            "estimate": {
                "modules": [
                    {
                        "name": "Backend",
                        "tasks": [
                            {
                                "name": "API",
                                "estimated_hours": 40,
                                "has_match": True,
                            }
                        ],
                    }
                ],
                "total_engineer_days": 5,
                "total_engineer_hours": 40,
                "confidence": "high",
            },
            "analysis_report": {
                "overall_confidence": "high",
                "grounded_task_ratio": 1.0,
                "weak_points": [],
                "summary": "looks good",
            },
            "proposal": "# Proposal body",
        }
    )
    assert "s13-demo" in text
    assert "Backend" in text
    assert "40h" in text
    assert "looks good" in text
    assert "Proposal body" in text


@pytest.mark.asyncio
async def test_install_stub_hours_is_deterministic() -> None:
    install_stub_hours()
    from app.services.estimation_graph.agents import hours as hours_mod

    first = await hours_mod.estimate_one(
        "M", "T", None, top_k=5, distance_threshold=0.5
    )
    second = await hours_mod.estimate_one(
        "M", "T", None, top_k=5, distance_threshold=0.5
    )
    assert isinstance(first, TaskHoursEstimateView)
    assert first.has_match is True
    assert first.estimated_hours == second.estimated_hours
    assert 8 <= (first.estimated_hours or 0) <= 80


@pytest.mark.asyncio
async def test_run_to_completion_auto_approves_both_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI auto-resume loop completes with MemorySaver + fakes (no network)."""
    monkeypatch.setattr(
        "app.services.estimation_graph.structured.complete_graph_structured",
        _FakeStructured(),
    )
    monkeypatch.setattr(
        "app.services.estimation_graph.agents.structure.get_async_openai_client",
        lambda settings: object(),
    )
    monkeypatch.setattr(
        "app.services.estimation_graph.agents.hours.get_async_openai_client",
        lambda settings: object(),
    )
    monkeypatch.setattr(
        "app.services.estimation_graph.agents.structure.run_structure_agent",
        _fake_structure,
    )
    install_stub_hours()
    monkeypatch.setenv("GRAPH_PROPOSAL_ENABLED", "true")
    get_settings.cache_clear()

    graph = build_graph(MemorySaver())
    state = await run_to_completion(graph, "A" * 200, "cli-e2e")

    assert state.get("status") == "validated"
    assert state.get("complexity") == "medium"
    assert state.get("proposal")
    task_hours = state.get("task_hours") or []
    assert len(task_hours) == 2
    assert all(row.get("has_match") for row in task_hours)

    snapshot = await graph.aget_state({"configurable": {"thread_id": "cli-e2e"}})
    assert not snapshot.next
