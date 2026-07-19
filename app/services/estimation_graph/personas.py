"""Optional didactic persona prefixes for graph workers (feature-067)."""

from __future__ import annotations

_PERSONAS: dict[str, str] = {
    "requirements_extractor": (
        "You are a requirements analyst extracting crisp, testable scope statements."
    ),
    "budget_searcher": (
        "You are a historical-evidence researcher. Search narrowly per requirement."
    ),
    "estimate_generator": (
        "You are an estimator. Cost only from evidence; never invent precedents."
    ),
    "coherence_validator": (
        "You are a coherence reviewer. Surface risk signals honestly."
    ),
    "proposal_agent": (
        "You are a delivery lead drafting an honest commercial proposal."
    ),
}


def persona_for(node_fn: str, *, enabled: bool) -> str | None:
    """Return the persona prefix for a worker, or ``None`` when disabled."""
    if not enabled:
        return None
    return _PERSONAS.get(node_fn)
