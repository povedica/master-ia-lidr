"""Tests for agentic estimation schemas and trace rendering."""

from __future__ import annotations

from app.services.agentic.agent_schemas import AgentStep, AgentTrace


def test_agent_trace_render_format() -> None:
    trace = AgentTrace(
        steps=[
            AgentStep(
                step=1,
                reasoning_summary="Decomposing transcript into backend, ERP, mobile app...",
                tool="search_budgets",
                tool_args={
                    "query": "business backend API orders routes",
                    "filters": {"sectors": None, "component_type": "backend"},
                },
                observation="found 2 budgets, top hours 1150.0, 940.0",
            ),
            AgentStep(
                step=2,
                reasoning_summary="Costing components with historical references.",
                tool="calculate_estimate",
                tool_args={
                    "components": [
                        {"name": "Business backend", "reference_amounts": [1150.0, 940.0]},
                    ]
                },
                observation="total=1265.0h across 1 components",
            ),
        ]
    )

    rendered = trace.render()

    assert rendered.startswith("STEP 1\n")
    assert "reasoning:   Decomposing transcript into backend, ERP, mobile app..." in rendered
    assert 'action:      search_budgets(' in rendered
    assert '"query": "business backend API orders routes"' in rendered
    assert "observation: found 2 budgets, top hours 1150.0, 940.0" in rendered
    assert "STEP 2\n" in rendered
    assert "action:      calculate_estimate(" in rendered


def test_agent_trace_render_empty_steps() -> None:
    assert "(no tool steps" in AgentTrace().render()
