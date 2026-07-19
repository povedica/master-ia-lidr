"""End-to-end multi-agent graph run, network-free (feature-066 Step 4).

MemorySaver checkpointer + fakes for every network dependency. Asserts pauses at
both human gates, Send fan-out row count, keyed reducer idempotency, recovery
path, and the gate-2 proposal route.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.config import get_settings
from app.schemas.rag_task_hours import TaskHoursEstimateView
from app.services.agentic.agent_schemas import (
    AgentModuleNode,
    AgentStructure,
    AgentTaskDerivation,
    AgentTaskHoursRun,
    AgentTaskNode,
    AgentTrace,
)
from app.services.estimation_graph.build import build_graph
from app.services.estimation_graph.schemas import (
    CommercialProposal,
    ComplexityClassification,
    ReliabilityReport,
)

TRANSCRIPT = "A" * 200
CONFIG = {"configurable": {"thread_id": "t1"}}


class _FakeStructured:
    """Scripted ``complete_graph_structured`` double keyed on the response model."""

    def __init__(self, *, complexity: str = "high") -> None:
        self._complexity = complexity
        self.calls: list[str] = []

    async def __call__(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type,
        model: str,
        settings: object,
    ):
        self.calls.append(response_model.__name__)
        if response_model is ComplexityClassification:
            return ComplexityClassification(
                complexity=self._complexity,  # type: ignore[arg-type]
                reformulated_transcript=(
                    "Build a backend, a mobile app and an ERP integration."
                ),
                reasoning="several disparate components",
            )
        if response_model is ReliabilityReport:
            return ReliabilityReport(
                overall_confidence="medium",
                grounded_task_ratio=1.0,
                weak_points=[],
                summary="looks reasonable",
            )
        if response_model is CommercialProposal:
            return CommercialProposal(
                title="RUTA",
                executive_summary="A logistics platform.",
                scope=["Backend", "Mobile"],
                total_engineer_days=20,
                body_markdown="# Proposal\n...",
            )
        raise AssertionError(f"unexpected response_model {response_model!r}")


def _structure(modules: dict[str, list[str]]):
    """Build a fake ``run_structure_agent`` returning the given module→task tree."""

    async def _run(brief, *, client, model, reasoning_effort="medium", persona=None):
        struct = AgentStructure(
            modules=[
                AgentModuleNode(
                    name=module_name,
                    tasks=[
                        AgentTaskNode(name=task_name, description=f"{task_name} scope")
                        for task_name in tasks
                    ],
                )
                for module_name, tasks in modules.items()
            ],
            confidence="high",
            reasoning="decomposed",
        )
        return struct, AgentTrace()

    return _run


def _estimate_one(hours_by_task: dict[str, int], *, no_match: set[str] | frozenset[str] = ()):
    """Fake ``estimate_one``: grounded hours per task, or ``has_match=False``."""

    async def _one(module, name, description, *, top_k, distance_threshold, **kwargs):
        if name in no_match:
            return TaskHoursEstimateView(module=module, task=name, has_match=False)
        return TaskHoursEstimateView(
            module=module,
            task=name,
            estimated_hours=hours_by_task.get(name, 40),
            reliability=0.85,
            has_match=True,
            dispersion=0.1,
            neighbors=[],
        )

    return _one


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    structured: _FakeStructured,
    structure_fn,
    estimate_one_fn,
    recovery_fn=None,
) -> None:
    monkeypatch.setattr(
        "app.services.estimation_graph.structured.complete_graph_structured",
        structured,
    )
    # Non-None client so structure / recovery agents proceed (themselves faked).
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
        structure_fn,
    )
    monkeypatch.setattr(
        "app.services.estimation_graph.agents.hours.estimate_one",
        estimate_one_fn,
    )
    if recovery_fn is not None:
        monkeypatch.setattr(
            "app.services.estimation_graph.agents.hours.run_task_hours_recovery_agent",
            recovery_fn,
        )


async def _start(graph):
    return await graph.ainvoke({"transcript": TRANSCRIPT, "estimation_id": "t1"}, CONFIG)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_gate2_estimate_overrides_recompute_totals(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire(
        monkeypatch,
        structured=_FakeStructured(),
        structure_fn=_structure({"Backend": ["API", "Auth"]}),
        estimate_one_fn=_estimate_one({"API": 80, "Auth": 40}),
    )
    graph = build_graph(MemorySaver())
    await _start(graph)
    await graph.ainvoke(Command(resume={"approved": True}), CONFIG)
    snap = await graph.aget_state(CONFIG)
    assert snap.values["estimate"]["total_engineer_hours"] == 120.0

    edited = [
        {
            "name": "Backend",
            "tasks": [
                {"name": "API", "estimated_hours": 160, "has_match": True},
                {"name": "Auth", "estimated_hours": 40, "has_match": True},
            ],
        }
    ]
    result = await graph.ainvoke(
        Command(
            resume={
                "validated": True,
                "estimate_overrides": {"modules": edited},
                "want_proposal": False,
            }
        ),
        CONFIG,
    )
    assert result["status"] == "validated"
    assert result["estimate"]["total_engineer_hours"] == 200.0
    assert result["estimate"]["total_engineer_days"] == 25
    assert result["estimate"]["confidence"] == "high"


@pytest.mark.asyncio
async def test_full_flow_pauses_at_both_gates_and_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured = _FakeStructured()
    _wire(
        monkeypatch,
        structured=structured,
        structure_fn=_structure({"Backend": ["API", "Auth"], "Mobile": ["App"]}),
        estimate_one_fn=_estimate_one({"API": 80, "Auth": 40, "App": 120}),
    )
    graph = build_graph(MemorySaver())

    await _start(graph)
    snap = await graph.aget_state(CONFIG)
    assert snap.next == ("human_gate_structure",)
    assert snap.interrupts[0].value["gate"] == "structure_review"
    assert snap.values["complexity"] == "high"
    assert snap.values["structure"]["modules"]

    await graph.ainvoke(Command(resume={"approved": True}), CONFIG)
    snap = await graph.aget_state(CONFIG)
    assert snap.next == ("human_gate_analysis",)
    assert snap.interrupts[0].value["gate"] == "final_review"
    assert len(snap.values["task_hours"]) == 3
    assert snap.values["estimate"]["total_engineer_days"] == round((80 + 40 + 120) / 8)
    assert snap.values["analysis_report"]["overall_confidence"] == "medium"

    result = await graph.ainvoke(
        Command(resume={"validated": True, "want_proposal": True}),
        CONFIG,
    )
    snap = await graph.aget_state(CONFIG)
    assert snap.next == ()
    assert result["status"] == "validated"
    assert result["proposal"].startswith("# Proposal")
    assert structured.calls == [
        "ComplexityClassification",
        "ReliabilityReport",
        "CommercialProposal",
    ]


@pytest.mark.asyncio
async def test_gate2_without_proposal_ends_without_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured = _FakeStructured()
    _wire(
        monkeypatch,
        structured=structured,
        structure_fn=_structure({"Backend": ["API"]}),
        estimate_one_fn=_estimate_one({"API": 40}),
    )
    graph = build_graph(MemorySaver())
    await _start(graph)
    await graph.ainvoke(Command(resume={"approved": True}), CONFIG)
    result = await graph.ainvoke(
        Command(resume={"validated": True, "want_proposal": False}),
        CONFIG,
    )

    snap = await graph.aget_state(CONFIG)
    assert snap.next == ()
    assert result["status"] == "validated"
    assert result.get("proposal") is None
    assert "CommercialProposal" not in structured.calls


@pytest.mark.asyncio
async def test_flagged_task_triggers_agentic_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    structured = _FakeStructured()
    recovery_calls: list[int] = []

    async def _recovery(flagged, **kwargs):
        recovery_calls.append(len(flagged))
        return AgentTaskHoursRun(
            derivations=[
                AgentTaskDerivation(
                    module=task.module,
                    task=task.task,
                    estimated_hours=64,
                    reliability=0.7,
                    has_match=True,
                )
                for task in flagged
            ],
            trace=AgentTrace(),
            iterations=1,
            stopped_reason="completed",
        )

    _wire(
        monkeypatch,
        structured=structured,
        structure_fn=_structure({"Backend": ["API", "Legacy"]}),
        estimate_one_fn=_estimate_one({"API": 40}, no_match={"Legacy"}),
        recovery_fn=_recovery,
    )
    graph = build_graph(MemorySaver())
    await _start(graph)
    await graph.ainvoke(Command(resume={"approved": True}), CONFIG)

    snap = await graph.aget_state(CONFIG)
    assert recovery_calls == [1]
    hours = {row["task"]: row["estimated_hours"] for row in snap.values["task_hours"]}
    assert hours == {"API": 40, "Legacy": 64}
    assert len(snap.values["task_hours"]) == 2
