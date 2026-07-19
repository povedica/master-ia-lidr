"""Wire and compile the supervisor/worker estimation graph (feature-067).

Topology:

    START → supervisor
      ├─Command→ requirements_extractor ─edge→ supervisor
      ├─Command→ budget_searcher        ─edge→ supervisor
      ├─Command→ estimate_generator     ─edge→ supervisor
      ├─Command→ coherence_validator    ─edge→ supervisor
      ├─Command→ human_review [interrupt] ─edge→ supervisor
      └─Command→ END
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.services.estimation_graph.agents.budget_searcher import build_budget_searcher
from app.services.estimation_graph.agents.coherence_validator import (
    build_coherence_validator,
)
from app.services.estimation_graph.agents.estimate_generator import (
    build_estimate_generator,
)
from app.services.estimation_graph.agents.human_review import human_review
from app.services.estimation_graph.agents.requirements_extractor import (
    build_requirements_extractor,
)
from app.services.estimation_graph.state import EstimationState
from app.services.estimation_graph.supervisor import supervisor as supervisor_node

Worker = Callable[[EstimationState], Awaitable[dict[str, Any]]]


def build_graph(
    checkpointer=None,
    *,
    complete_fn=None,
    search_budgets_fn=None,
    calculate_estimate_fn=None,
    validate_estimate_fn=None,
    retrieval_backend=None,
    confidence_threshold: float | None = None,
):
    """Build and compile the supervisor/worker estimation graph.

    ``checkpointer`` persists state per ``thread_id`` (``AsyncPostgresSaver`` in
    the app, ``MemorySaver`` in tests). Optional callables inject fakes for the
    default network-free suite.
    """
    requirements_extractor = build_requirements_extractor(complete_fn=complete_fn)
    budget_searcher = build_budget_searcher(
        search_budgets_fn,
        backend=retrieval_backend,
    )
    estimate_generator = build_estimate_generator(
        calculate_estimate_fn=calculate_estimate_fn,
    )
    coherence_validator = build_coherence_validator(
        validate_estimate_fn=validate_estimate_fn,
        confidence_threshold=confidence_threshold,
    )

    def _supervisor(state: EstimationState):
        return supervisor_node(state, confidence_threshold=confidence_threshold)

    builder = StateGraph(EstimationState)
    builder.add_node("supervisor", _supervisor)
    builder.add_node("requirements_extractor", requirements_extractor)
    builder.add_node("budget_searcher", budget_searcher)
    builder.add_node("estimate_generator", estimate_generator)
    builder.add_node("coherence_validator", coherence_validator)
    builder.add_node("human_review", human_review)

    builder.add_edge(START, "supervisor")
    for node in (
        "requirements_extractor",
        "budget_searcher",
        "estimate_generator",
        "coherence_validator",
        "human_review",
    ):
        builder.add_edge(node, "supervisor")

    # Terminal transitions use Command(goto=END) from the supervisor.
    _ = END
    return builder.compile(checkpointer=checkpointer)
