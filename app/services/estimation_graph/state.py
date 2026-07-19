"""Shared typed state for the Session 13 estimation graph (feature-066)."""

from __future__ import annotations

import operator
from typing import Annotated, Optional

from typing_extensions import TypedDict


class Component(TypedDict):
    """One functional component the project decomposes into."""

    name: str
    category: str


class BudgetMatch(TypedDict):
    """A historical reference budget retrieved for a component."""

    component: str
    reference_budget_id: Optional[str]
    amount: float
    distance: float


def merge_task_hours(existing: list[dict] | None, new: list[dict] | None) -> list[dict]:
    """Keyed reducer for the per-task hours fan-out accumulator.

    Keyed by ``(module, task)``, last-write-wins. Idempotent across resumes that
    re-enter the fan-out (unlike plain ``operator.add``).
    """
    by_key: dict[tuple[str | None, str | None], dict] = {
        (row.get("module"), row.get("task")): row for row in (existing or [])
    }
    for row in new or []:
        by_key[(row.get("module"), row.get("task"))] = row
    return list(by_key.values())


class EstimationState(TypedDict, total=False):
    """State threaded through the multi-agent estimation graph."""

    transcript: str
    estimation_id: str

    complexity: Optional[str]
    reformulated_transcript: Optional[str]

    requirements: list[str]
    components: list[Component]
    budget_matches: Annotated[list[BudgetMatch], operator.add]

    structure: Optional[dict]
    approved_modules: Optional[list[dict]]
    gate1_decision: Optional[dict]

    task_hours: Annotated[list[dict], merge_task_hours]
    estimate: Optional[dict]

    analysis_report: Optional[dict]
    gate2_decision: Optional[dict]

    proposal: Optional[str]

    status: Optional[str]
    errors: Annotated[list[str], operator.add]
