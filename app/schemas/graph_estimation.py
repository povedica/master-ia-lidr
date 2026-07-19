"""Public HTTP contract for the Session 13 multi-agent estimation graph.

Mirrors official ``domain/schemas/graph_estimation.py``: start / resume / state
plus the live stream / progress / proposal surface (Step 8).
"""

from __future__ import annotations

from typing import Literal

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


class ActivityEntry(BaseModel):
    """One didactic line of what an agent just did (see ``activity.py``)."""

    seq: int = 0
    node: str
    label: str
    message: str
    ts: str | None = None


class GraphProgress(GraphRunState):
    """Live progress of a background-streamed run: ``GraphRunState`` + activity.

    ``state`` gains ``"running"`` — mid-leg between gates while the panel fills.
    """

    state: Literal["running", "paused", "completed"]  # type: ignore[assignment]
    activity: list[ActivityEntry] = Field(default_factory=list)


class GraphProposalResponse(BaseModel):
    """Commercial proposal from ``POST …/graph/{id}/proposal``.

    Generated on demand over the run's already-validated estimate (no graph re-run).
    """

    estimation_id: str
    title: str
    executive_summary: str
    scope: list[str] = Field(default_factory=list)
    total_engineer_days: int | None = None
    body_markdown: str
