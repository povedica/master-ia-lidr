"""Unit tests for Session 13 two-phase agent APIs (feature-066)."""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.services.agentic.agent_loop import (
    run_structure_agent,
    run_task_hours_recovery_agent,
)
from app.services.agentic.agent_schemas import (
    AgentModuleNode,
    AgentStructure,
    AgentTaskNode,
    AgentTaskRef,
    SearchBudgetsArgs,
)
from app.services.agentic.agent_tools import derive_task_hours
from app.services.rag_task_hours import consensus_hours


def _function_call(name: str, call_id: str, arguments: dict):
    return SimpleNamespace(
        type="function_call",
        name=name,
        call_id=call_id,
        arguments=json.dumps(arguments),
    )


def _reasoning(text: str):
    return SimpleNamespace(type="reasoning", summary=[SimpleNamespace(text=text)])


def _message():
    return SimpleNamespace(type="message", role="assistant", content=[])


class _FakeResponses:
    def __init__(self, scripted_outputs: list[list] | None = None, parsed=None):
        self._scripted = scripted_outputs or []
        self._parsed = parsed
        self._i = 0
        self.create_calls: list[dict] = []
        self.parse_calls: list[dict] = []

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        output = self._scripted[min(self._i, len(self._scripted) - 1)]
        self._i += 1
        return SimpleNamespace(output=output, id=f"resp_{self._i}")

    async def parse(self, **kwargs):
        self.parse_calls.append(kwargs)
        return SimpleNamespace(
            output_parsed=self._parsed,
            output=[_reasoning("Split the project into auth and reporting.")],
        )


class _FakeClient:
    def __init__(self, responses: _FakeResponses):
        self.responses = responses


async def _stub_backend(args: SearchBudgetsArgs) -> list[dict]:
    return [
        {"id": 1, "estimated_hours": 100, "content_preview": "x", "distance": 0.1},
        {"id": 2, "estimated_hours": 140, "content_preview": "y", "distance": 0.3},
    ]


async def test_structure_agent_returns_tree_and_thin_trace() -> None:
    parsed = AgentStructure(
        modules=[
            AgentModuleNode(
                name="Auth",
                description="Access",
                tasks=[AgentTaskNode(name="OAuth backend"), AgentTaskNode(name="RBAC")],
            )
        ],
        confidence="high",
        reasoning="Standard SaaS shape.",
    )
    fake = _FakeResponses(parsed=parsed)
    structure, trace = await run_structure_agent(
        "a project brief",
        client=_FakeClient(fake),
        model="gpt-5-mini",
    )
    assert len(structure.modules) == 1
    assert [task.name for task in structure.modules[0].tasks] == ["OAuth backend", "RBAC"]
    assert fake.parse_calls and not fake.create_calls
    assert len(trace.steps) == 1
    assert trace.steps[0].tool == "propose_structure"
    assert "2 tasks" in trace.steps[0].observation
    assert trace.steps[0].reasoning_summary is not None


def _recovery_script() -> list[list]:
    return [
        [
            _reasoning("Search analogs for each flagged task."),
            _function_call("search_budgets", "s1", {"query": "oauth backend", "filters": None}),
            _function_call("search_budgets", "s2", {"query": "reporting", "filters": None}),
        ],
        [
            _function_call(
                "derive_task_hours",
                "d1",
                {
                    "module": "Auth",
                    "task": "OAuth backend",
                    "neighbors": [
                        {
                            "estimated_hours": 100,
                            "distance": 0.1,
                            "source_id": 1,
                            "budget_id": None,
                        },
                        {
                            "estimated_hours": 140,
                            "distance": 0.3,
                            "source_id": 2,
                            "budget_id": None,
                        },
                    ],
                },
            ),
        ],
        [_message()],
    ]


def _flagged() -> list[AgentTaskRef]:
    return [
        AgentTaskRef(module="Auth", task="OAuth backend", reason="no analog"),
        AgentTaskRef(module="Reporting", task="Dashboards", reason="low reliability"),
    ]


async def test_recovery_runs_search_then_derive_and_captures_derivations() -> None:
    fake = _FakeResponses(_recovery_script())
    run = await run_task_hours_recovery_agent(
        _flagged(),
        client=_FakeClient(fake),
        model="gpt-5-mini",
        max_iterations=10,
        retrieval_backend=_stub_backend,
        consensus_fn=consensus_hours,
    )
    tools = [step.tool for step in run.trace.steps]
    assert tools.count("search_budgets") == 2
    assert "derive_task_hours" in tools
    assert run.stopped_reason == "completed"

    assert len(run.derivations) == 1
    derivation = run.derivations[0]
    assert (derivation.module, derivation.task) == ("Auth", "OAuth backend")
    assert derivation.has_match is True
    expected_hours, expected_reliability, _ = consensus_hours([(100, 0.1), (140, 0.3)])
    assert derivation.estimated_hours == expected_hours
    assert derivation.reliability == expected_reliability


async def test_recovery_empty_flagged_list_short_circuits() -> None:
    fake = _FakeResponses()
    run = await run_task_hours_recovery_agent(
        [],
        client=_FakeClient(fake),
        model="gpt-5-mini",
        retrieval_backend=_stub_backend,
        consensus_fn=consensus_hours,
    )
    assert run.iterations == 0
    assert run.derivations == []
    assert not fake.create_calls


async def test_recovery_call_ids_are_echoed_back() -> None:
    fake = _FakeResponses(_recovery_script())
    await run_task_hours_recovery_agent(
        _flagged(),
        client=_FakeClient(fake),
        model="gpt-5-mini",
        retrieval_backend=_stub_backend,
        consensus_fn=consensus_hours,
    )
    second_call_input = fake.create_calls[1]["input"]
    echoed = {item["call_id"] for item in second_call_input}
    assert echoed == {"s1", "s2"}
    for item in second_call_input:
        assert item["type"] == "function_call_output"
        assert isinstance(item["output"], str)


async def test_recovery_max_iterations_safeguard_stops_loop() -> None:
    never_stops = [[_function_call("search_budgets", "x", {"query": "loop", "filters": None})]]
    fake = _FakeResponses(never_stops)
    run = await run_task_hours_recovery_agent(
        _flagged(),
        client=_FakeClient(fake),
        model="gpt-5-mini",
        max_iterations=3,
        retrieval_backend=_stub_backend,
        consensus_fn=consensus_hours,
    )
    assert run.stopped_reason == "max_iterations"
    assert run.iterations == 3


async def test_recovery_bad_tool_args_do_not_crash_the_loop() -> None:
    script = [
        [
            _function_call(
                "derive_task_hours",
                "bad",
                {"module": "Auth"},  # missing task + neighbors
            )
        ],
        [_message()],
    ]
    fake = _FakeResponses(script)
    run = await run_task_hours_recovery_agent(
        _flagged(),
        client=_FakeClient(fake),
        model="gpt-5-mini",
        retrieval_backend=_stub_backend,
        consensus_fn=consensus_hours,
    )
    assert any("error" in step.observation for step in run.trace.steps)
    assert run.derivations == []


def test_derive_task_hours_matches_consensus_exactly() -> None:
    result = derive_task_hours(
        {
            "module": "Auth",
            "task": "OAuth",
            "neighbors": [
                {"estimated_hours": 100, "distance": 0.1, "source_id": 1, "budget_id": None},
                {"estimated_hours": 140, "distance": 0.3, "source_id": 2, "budget_id": None},
            ],
        },
        consensus_fn=consensus_hours,
    )
    hours, reliability, dispersion = consensus_hours([(100, 0.1), (140, 0.3)])
    assert result["has_match"] is True
    assert result["estimated_hours"] == hours
    assert result["reliability"] == reliability
    assert result["dispersion"] == dispersion


def test_derive_task_hours_no_neighbors_is_no_match() -> None:
    result = derive_task_hours(
        {"module": "Auth", "task": "OAuth", "neighbors": []},
        consensus_fn=consensus_hours,
    )
    assert result["has_match"] is False
    assert "estimated_hours" not in result
