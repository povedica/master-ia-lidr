"""The agent's tools: flat Responses schemas + Python implementations."""

from __future__ import annotations

import logging
import statistics
from collections.abc import Awaitable, Callable
from typing import Any

from app.services.agentic.agent_schemas import (
    CalculateEstimateArgs,
    DeriveTaskHoursArgs,
    SearchBudgetsArgs,
    ValidateEstimateArgs,
)

logger = logging.getLogger(__name__)

CONTINGENCY_FACTOR = 0.15
CONTENT_PREVIEW_CHARS = 160

SEARCH_BUDGETS_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "search_budgets",
    "description": (
        "Search historical project budgets for work analogous to ONE component or "
        "requirement, and return the matching items with their recorded effort in "
        "engineer-hours. Call this once per component you need to cost (e.g. once "
        "for the payments backend, once for the mobile app). Use a focused, "
        "component-specific query — not the whole project. Returns a list of "
        "historical items, each with an id, a text preview, its sector and its "
        "recorded engineer-hours; use those hours as the reference_amounts for "
        "calculate_estimate."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Natural-language description of the single component to find "
                    "budgets for, e.g. 'OAuth2 authentication backend with JWT and "
                    "multi-tenant token isolation'."
                ),
            },
            "filters": {
                "type": ["object", "null"],
                "description": "Optional structural filters. Pass null to search across everything.",
                "properties": {
                    "sectors": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": "Restrict to these client sectors, e.g. ['logistics'].",
                    },
                    "component_type": {
                        "type": ["string", "null"],
                        "description": "Free-text hint about the kind of component, e.g. 'mobile app'.",
                    },
                },
                "required": ["sectors", "component_type"],
                "additionalProperties": False,
            },
        },
        "required": ["query", "filters"],
        "additionalProperties": False,
    },
    "strict": True,
}

CALCULATE_ESTIMATE_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "calculate_estimate",
    "description": (
        "Deterministically compute an effort estimate in engineer-hours from a set "
        "of components and their historical reference amounts. For each component it "
        "takes the median of the reference_amounts and adds a fixed contingency "
        "buffer; it then sums the components into a total. Call this once you have "
        "gathered reference amounts (from search_budgets) for every component. This "
        "does NOT call a model — it is pure arithmetic, so its output is reproducible."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "components": {
                "type": "array",
                "description": "The components to cost.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Component name."},
                        "reference_amounts": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": (
                                "Historical engineer-hours for analogous work, taken "
                                "from search_budgets results. May be empty if nothing "
                                "was found (the component is then flagged)."
                            ),
                        },
                    },
                    "required": ["name", "reference_amounts"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["components"],
        "additionalProperties": False,
    },
    "strict": True,
}

VALIDATE_ESTIMATE_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "validate_estimate",
    "description": (
        "Run sanity-check guardrails over a finished estimate before returning it. "
        "It flags components with no historical reference, components whose hours are "
        "far outside the range of their references, a total that does not match the "
        "sum of the components, and non-positive or implausibly large totals. Call "
        "this as the LAST step, once you have a full estimate, and address any issues "
        "it reports before giving your final answer. Returns {ok, issues}."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "components": {
                "type": "array",
                "description": "The estimate's components, with their final hours and references.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "estimated_hours": {"type": "number"},
                        "reference_amounts": {
                            "type": "array",
                            "items": {"type": "number"},
                        },
                    },
                    "required": ["name", "estimated_hours", "reference_amounts"],
                    "additionalProperties": False,
                },
            },
            "total_hours": {
                "type": "number",
                "description": "The estimate's grand total in engineer-hours.",
            },
        },
        "required": ["components", "total_hours"],
        "additionalProperties": False,
    },
    "strict": True,
}

DERIVE_TASK_HOURS_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "derive_task_hours",
    "description": (
        "Deterministically derive the engineer-hours for ONE task from the "
        "historical analogs you found with search_budgets. It computes a "
        "distance-weighted consensus of the neighbours' hours (closer analogs "
        "count more) plus a 0..1 reliability score — the SAME arithmetic the "
        "standard pipeline uses. Pass the neighbours exactly as search_budgets "
        "returned them (each with its estimated_hours AND its distance). Call this "
        "once you have gathered analogs for the task. This does NOT call a model — "
        "it is pure arithmetic, so its output is reproducible. If you found no "
        "usable analog, do NOT call this with an empty list; report the task as "
        "unresolved instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "module": {"type": "string", "description": "Module the task belongs to."},
            "task": {"type": "string", "description": "Task name (echoed back)."},
            "neighbors": {
                "type": "array",
                "description": "Historical analogs from search_budgets that anchor this task.",
                "items": {
                    "type": "object",
                    "properties": {
                        "estimated_hours": {
                            "type": "integer",
                            "description": "Recorded engineer-hours for the analog.",
                        },
                        "distance": {
                            "type": "number",
                            "description": "Cosine distance from search_budgets (lower = closer).",
                        },
                        "source_id": {
                            "type": ["integer", "null"],
                            "description": "DB id of the analog chunk (the search result 'id').",
                        },
                        "budget_id": {
                            "type": ["string", "null"],
                            "description": "Traceable parent budget id, if any.",
                        },
                    },
                    "required": ["estimated_hours", "distance", "source_id", "budget_id"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["module", "task", "neighbors"],
        "additionalProperties": False,
    },
    "strict": True,
}

# Task-focused copy of search_budgets for the Session 13 recovery loop.
SEARCH_BUDGETS_HOURS_TOOL: dict[str, Any] = {
    **SEARCH_BUDGETS_TOOL,
    "description": (
        "Search historical project tasks for work analogous to ONE task you are "
        "trying to cost, and return the matching items with their recorded effort "
        "in engineer-hours. Call this once per task you need to ground. Use a "
        "focused, task-specific query — reformulate it (different wording, "
        "synonyms, or drop/relax a filter) if the first search finds nothing. "
        "Returns a list of historical items, each with an id, a text preview, its "
        "sector, its recorded engineer-hours and its distance; pass those "
        "(hours + distance) as the neighbors for derive_task_hours."
    ),
}

VALIDATE_ESTIMATE_HOURS_TOOL: dict[str, Any] = {
    **VALIDATE_ESTIMATE_TOOL,
    "description": (
        "Run sanity-check guardrails over the hours you recovered before finishing. "
        "It flags tasks with no historical reference, tasks whose hours are far "
        "outside the range of their references, a total that does not match the sum "
        "of the tasks, and non-positive or implausibly large totals. Call this as "
        "the LAST step, once you have derived hours for the tasks you could ground, "
        "and address any issues it reports. Returns {ok, issues}."
    ),
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    SEARCH_BUDGETS_TOOL,
    CALCULATE_ESTIMATE_TOOL,
    VALIDATE_ESTIMATE_TOOL,
]

STRUCTURE_TOOL_SCHEMAS: list[dict[str, Any]] = []
HOURS_TOOL_SCHEMAS: list[dict[str, Any]] = [
    SEARCH_BUDGETS_HOURS_TOOL,
    DERIVE_TASK_HOURS_TOOL,
    VALIDATE_ESTIMATE_HOURS_TOOL,
]

RetrievalBackend = Callable[[SearchBudgetsArgs], Awaitable[list[dict[str, Any]]]]
ConsensusFn = Callable[[list[tuple[int, float]]], tuple[int, float, float]]


async def search_budgets(
    raw_args: dict[str, Any],
    *,
    backend: RetrievalBackend,
) -> dict[str, Any]:
    """Retrieve historical budget items for one component."""
    args = SearchBudgetsArgs.model_validate(raw_args)
    items = await backend(args)
    hours = [item["estimated_hours"] for item in items if item.get("estimated_hours") is not None]
    summary = (
        f"{len(items)} historical items for {args.query!r}; hours={hours}"
        if items
        else f"no historical items for {args.query!r}"
    )
    logger.info(
        "agent_tool_search_budgets",
        extra={"query": args.query, "results": len(items)},
    )
    return {"items": items, "count": len(items), "summary": summary}


def calculate_estimate(raw_args: dict[str, Any]) -> dict[str, Any]:
    """Deterministically cost the components. No LLM."""
    args = CalculateEstimateArgs.model_validate(raw_args)
    breakdown: list[dict[str, Any]] = []
    total = 0.0
    for component in args.components:
        refs = component.reference_amounts
        if refs:
            central = statistics.median(refs)
            hours = round(central * (1 + CONTINGENCY_FACTOR), 1)
            flagged = False
        else:
            hours = 0.0
            flagged = True
        total += hours
        breakdown.append(
            {
                "name": component.name,
                "reference_count": len(refs),
                "estimated_hours": hours,
                "unbudgeted": flagged,
            }
        )
    total = round(total, 1)
    logger.info(
        "agent_tool_calculate_estimate",
        extra={"components": len(breakdown), "total_hours": total},
    )
    return {
        "components": breakdown,
        "total_hours": total,
        "contingency_factor": CONTINGENCY_FACTOR,
        "summary": f"total={total}h across {len(breakdown)} components",
    }


def validate_estimate(raw_args: dict[str, Any]) -> dict[str, Any]:
    """S4-style guardrails over the final estimate. No LLM."""
    args = ValidateEstimateArgs.model_validate(raw_args)
    issues: list[str] = []

    component_sum = 0.0
    for component in args.components:
        component_sum += component.estimated_hours
        if not component.reference_amounts:
            issues.append(f"{component.name!r} has no historical reference (unbudgeted).")
            continue
        low = min(component.reference_amounts) * 0.5
        high = max(component.reference_amounts) * 2.0
        if not (low <= component.estimated_hours <= high):
            issues.append(
                f"{component.name!r} estimate {component.estimated_hours}h is outside the "
                f"plausible range [{round(low, 1)}, {round(high, 1)}]h implied by its references."
            )

    if args.total_hours <= 0:
        issues.append("Total hours is non-positive.")
    if abs(component_sum - args.total_hours) > 0.5:
        issues.append(
            f"Total {args.total_hours}h does not match the sum of components "
            f"({round(component_sum, 1)}h)."
        )
    if args.total_hours > 20_000:
        issues.append(f"Total {args.total_hours}h is implausibly large for one project.")

    ok = not issues
    logger.info(
        "agent_tool_validate_estimate",
        extra={"ok": ok, "issues": len(issues)},
    )
    return {
        "ok": ok,
        "issues": issues,
        "summary": "estimate passed all guardrails" if ok else f"{len(issues)} issue(s) found",
    }


def derive_task_hours(raw_args: dict[str, Any], *, consensus_fn: ConsensusFn) -> dict[str, Any]:
    """Distance-weighted consensus over analogs. No LLM."""
    args = DeriveTaskHoursArgs.model_validate(raw_args)
    if not args.neighbors:
        return {
            "module": args.module,
            "task": args.task,
            "has_match": False,
            "summary": f"no neighbours supplied for {args.task!r}; task left unresolved",
        }
    pairs = [(n.estimated_hours, n.distance) for n in args.neighbors]
    hours, reliability, dispersion = consensus_fn(pairs)
    logger.info(
        "agent_tool_derive_task_hours",
        extra={"task": args.task, "neighbors": len(pairs), "hours": hours},
    )
    return {
        "module": args.module,
        "task": args.task,
        "estimated_hours": hours,
        "reliability": reliability,
        "dispersion": dispersion,
        "has_match": True,
        "summary": (
            f"{args.task!r}: {hours}h (reliability {reliability}) from {len(pairs)} analogs"
        ),
    }


async def dispatch_tool(
    name: str,
    raw_args: dict[str, Any],
    *,
    backend: RetrievalBackend,
    consensus_fn: ConsensusFn | None = None,
) -> dict[str, Any]:
    """Route a tool call to its implementation."""
    if name == "search_budgets":
        return await search_budgets(raw_args, backend=backend)
    if name == "calculate_estimate":
        return calculate_estimate(raw_args)
    if name == "derive_task_hours":
        if consensus_fn is None:
            raise ValueError("consensus_fn is required for derive_task_hours")
        return derive_task_hours(raw_args, consensus_fn=consensus_fn)
    if name == "validate_estimate":
        return validate_estimate(raw_args)
    raise ValueError(f"Unknown tool: {name!r}")
