"""Public HTTP contract for the Session 13 multi-agent estimation graph.

These mirror the official ``domain/schemas/graph_estimation.py`` models used by
start / resume / state. Stream/progress/proposal models are deferred to Step 8.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GraphEstimateRequest(BaseModel):
    """Payload for ``POST /api/v1/estimate/graph``."""

    transcript: str = Field(min_length=100, max_length=50_000)
    # Used as the checkpointer ``thread_id`` so a re-run resumes the same thread.
    # Defaults to a fresh UUID in the router when omitted.
    estimation_id: str | None = Field(default=None, max_length=128)


class GraphResumeRequest(BaseModel):
    """Payload for ``POST /api/v1/estimate/graph/{estimation_id}/resume``.

    ``decision`` is the human's answer to whichever gate the run is paused at.
    Shape depends on ``pending_gate.gate``:

    * ``structure_review`` → ``{"approved": bool, "modules": [...]}``
    * ``final_review`` → ``{"validated": bool, "estimate_overrides": {...},
      "want_proposal": bool}``
    """

    decision: dict = Field(default_factory=dict)


class PendingGate(BaseModel):
    """The human gate a paused run is waiting on (the ``interrupt`` payload)."""

    gate: str  # "structure_review" | "final_review"
    estimation_id: str
    payload: dict = Field(default_factory=dict)


class GraphRunState(BaseModel):
    """Snapshot of a multi-agent run: paused at a gate, or completed.

    Returned by START, RESUME, and the read-only STATE endpoint.
    """

    estimation_id: str
    state: str  # "paused" | "completed"
    pending_gate: PendingGate | None = None
    complexity: str | None = None
    structure: dict | None = None
    task_hours: list[dict] = Field(default_factory=list)
    estimate: dict | None = None
    analysis_report: dict | None = None
    proposal: str | None = None
    status: str | None = None  # "validated" | "needs_review"
    errors: list[str] = Field(default_factory=list)
