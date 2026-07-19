"""Compiled supervisor/worker topology (feature-067)."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from app.services.estimation_graph.build import build_graph


def test_build_graph_compiles_supervisor_worker_topology() -> None:
    graph = build_graph(MemorySaver())
    nodes = set(graph.get_graph().nodes)
    assert "supervisor" in nodes
    assert "requirements_extractor" in nodes
    assert "budget_searcher" in nodes
    assert "estimate_generator" in nodes
    assert "coherence_validator" in nodes
    assert "human_review" in nodes
    assert "classifier_agent" not in nodes
    assert "human_gate_structure" not in nodes
    assert "create_supervisor" not in repr(graph).lower()


def test_build_graph_accepts_injected_worker_dependencies() -> None:
    async def complete(**kwargs):
        raise AssertionError("should not run in this compile-only test")

    graph = build_graph(MemorySaver(), complete_fn=complete)
    assert graph is not None
