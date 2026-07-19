"""``budget_searcher`` — historical evidence worker (``search_budgets`` only)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.services.agentic.agent_tools import search_budgets as default_search_budgets
from app.services.agentic.retrieval_adapter import (
    RetrievalBackend,
    load_stub_retrieval_backend,
)
from app.services.estimation_graph.state import BudgetMatch, EstimationState

logger = logging.getLogger(__name__)

SearchBudgetsFn = Callable[..., Awaitable[dict[str, Any]]]


def build_budget_searcher(
    search_budgets_fn: SearchBudgetsFn | None = None,
    *,
    backend: RetrievalBackend | None = None,
) -> Callable[[EstimationState], Awaitable[dict[str, Any]]]:
    """Build a worker that may invoke only ``search_budgets``."""

    search_fn = search_budgets_fn or default_search_budgets

    async def budget_searcher(state: EstimationState) -> dict[str, Any]:
        requirements = state.get("requirements") or []
        retrieval = backend
        if retrieval is None and search_budgets_fn is None:
            retrieval = load_stub_retrieval_backend()

        matches: list[BudgetMatch] = []
        for index, requirement in enumerate(requirements):
            req_id, text, component = _requirement_fields(requirement, index)
            raw_args = {"query": text}
            if retrieval is None:
                result = await search_fn(raw_args)
            else:
                result = await search_fn(raw_args, backend=retrieval)
            items = result.get("items") or []
            if not items:
                matches.append(
                    {
                        "requirement_id": req_id,
                        "reference_budget_id": None,
                        "amount": 0.0,
                        "distance": 1.0,
                        "component": component,
                        "no_match": True,
                    }
                )
                continue
            for item in items:
                matches.append(
                    {
                        "requirement_id": req_id,
                        "reference_budget_id": _item_id(item),
                        "amount": float(item.get("estimated_hours") or 0.0),
                        "distance": float(item.get("distance") or 0.0),
                        "component": component,
                        "no_match": False,
                    }
                )

        logger.info(
            "graph_budget_searcher_done",
            extra={
                "requirement_count": len(requirements),
                "match_count": len(matches),
                "tool": "search_budgets",
            },
        )
        return {
            "budget_matches": matches,
            "search_attempted": True,
            "completed_workers": ["budget_searcher"],
            "agent_contributions": [
                {
                    "worker": "budget_searcher",
                    "tool": "search_budgets",
                    "summary": f"{len(matches)} match rows for {len(requirements)} requirements",
                }
            ],
        }

    return budget_searcher


def _requirement_fields(requirement: Any, index: int) -> tuple[str, str, str]:
    if isinstance(requirement, str):
        text = requirement.strip()
        return f"req-{index + 1}", text, text[:80] or f"requirement-{index + 1}"
    if isinstance(requirement, dict):
        text = str(requirement.get("text") or requirement.get("name") or "").strip()
        req_id = str(requirement.get("id") or f"req-{index + 1}")
        component = str(requirement.get("category") or text[:80] or req_id)
        return req_id, text or req_id, component
    text = str(requirement)
    return f"req-{index + 1}", text, text[:80]


def _item_id(item: dict[str, Any]) -> str | None:
    value = item.get("id") or item.get("reference_budget_id")
    return str(value) if value is not None else None
