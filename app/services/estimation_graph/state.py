"""Shared typed state for the supervisor/worker estimation graph (feature-067).

Legacy Session 13 fields remain optional until the topology retirement step so
existing graph modules keep compiling during the migration.
"""

from __future__ import annotations

import operator
from typing import Annotated, NotRequired, Optional

from typing_extensions import TypedDict


class Component(TypedDict):
    """One functional component the project decomposes into."""

    name: str
    category: str


class BudgetMatch(TypedDict, total=False):
    """A historical reference (or explicit no-match) for one requirement."""

    requirement_id: str
    reference_budget_id: Optional[str]
    amount: float
    distance: float
    component: str
    no_match: bool


class AgentContribution(TypedDict, total=False):
    """Append-only record of a worker's visible output."""

    worker: str
    summary: str
    tool: str


def merge_budget_matches(
    existing: list[BudgetMatch] | None, new: list[BudgetMatch] | None
) -> list[BudgetMatch]:
    """Keyed reducer for historical matches.

    Identity is ``(requirement_id, reference_budget_id)``. Last-write-wins so
    resume / re-entry does not silently duplicate rows. ``reference_budget_id``
    may be ``None`` for explicit no-match markers.
    """
    by_key: dict[tuple[str | None, str | None], BudgetMatch] = {
        (row.get("requirement_id"), row.get("reference_budget_id")): row
        for row in (existing or [])
    }
    for row in new or []:
        by_key[(row.get("requirement_id"), row.get("reference_budget_id"))] = row
    return list(by_key.values())


def merge_agent_contributions(
    existing: list[AgentContribution] | None,
    new: list[AgentContribution] | None,
) -> list[AgentContribution]:
    """Append-only reducer for worker contribution records."""
    return list(existing or []) + list(new or [])


def merge_completed_workers(
    existing: list[str] | None, new: list[str] | None
) -> list[str]:
    """Set-union reducer so worker completion markers stay resume-safe."""
    return sorted(set(existing or []) | set(new or []))


def merge_task_hours(existing: list[dict] | None, new: list[dict] | None) -> list[dict]:
    """Legacy S13 keyed reducer retained until topology retirement."""
    by_key: dict[tuple[str | None, str | None], dict] = {
        (row.get("module"), row.get("task")): row for row in (existing or [])
    }
    for row in new or []:
        by_key[(row.get("module"), row.get("task"))] = row
    return list(by_key.values())


class EstimationState(TypedDict, total=False):
    """State threaded through the supervisor/worker estimation graph."""

    transcript: str
    estimation_id: str

    # Structured requirements produced by requirements_extractor.
    # Prefer list[dict] with stable ids; plain strings remain tolerated briefly.
    requirements: list

    budget_matches: Annotated[list[BudgetMatch], merge_budget_matches]
    estimate: Optional[dict]
    validation: Optional[dict]
    confidence: Optional[float]

    status: Optional[str]  # running | awaiting_human_review | completed | rejected
    completed_workers: Annotated[list[str], merge_completed_workers]
    agent_contributions: Annotated[list[AgentContribution], operator.add]

    human_review: Optional[dict]
    human_resolution: Optional[dict]
    human_adjustment_validated: bool

    # Routing / observability metadata for the supervisor.
    search_attempted: bool
    last_route: Optional[str]
    route_reason: Optional[str]
    supervisor_decisions: Annotated[list[dict], operator.add]

    errors: Annotated[list[str], operator.add]

    # --- Legacy Session 13 fields (removed when S13 agents are retired) ---
    complexity: NotRequired[Optional[str]]
    reformulated_transcript: NotRequired[Optional[str]]
    components: NotRequired[list[Component]]
    structure: NotRequired[Optional[dict]]
    approved_modules: NotRequired[Optional[list[dict]]]
    gate1_decision: NotRequired[Optional[dict]]
    task_hours: NotRequired[Annotated[list[dict], merge_task_hours]]
    analysis_report: NotRequired[Optional[dict]]
    gate2_decision: NotRequired[Optional[dict]]
    proposal: NotRequired[Optional[str]]
