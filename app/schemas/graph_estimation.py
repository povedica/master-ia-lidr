"""Public HTTP contract for the supervisor/worker estimation graph.

Start / resume / state plus the live stream / progress / proposal surface.
Session 14 (feature-067) uses typed human resolutions and business ``status``
values ``awaiting_human_review|completed|rejected``.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, model_validator


class GraphEstimateRequest(BaseModel):
    """Payload for ``POST /api/v1/estimate/graph``."""

    transcript: str = Field(min_length=100, max_length=50_000)
    # Used as the checkpointer ``thread_id`` so a re-run resumes the same thread.
    # Defaults to a fresh UUID in the router when omitted.
    estimation_id: str | None = Field(default=None, max_length=128)


class ApproveResolution(BaseModel):
    """Human accepts the proposed estimate."""

    action: Literal["approve"] = "approve"
    comment: str | None = None


class AdjustResolution(BaseModel):
    """Human supplies an adjusted estimate to fold into shared state."""

    action: Literal["adjust"] = "adjust"
    adjusted_estimate: dict[str, Any]
    comment: str | None = None


class RejectResolution(BaseModel):
    """Human rejects the run; graph finishes with status=rejected."""

    action: Literal["reject"] = "reject"
    comment: str | None = None


HumanResolution = Annotated[
    Union[ApproveResolution, AdjustResolution, RejectResolution],
    Field(discriminator="action"),
]

_HUMAN_RESOLUTION_ADAPTER: TypeAdapter[ApproveResolution | AdjustResolution | RejectResolution] = (
    TypeAdapter(HumanResolution)
)


def parse_human_resolution(
    payload: dict[str, Any],
) -> ApproveResolution | AdjustResolution | RejectResolution:
    """Validate a resume payload as a discriminated human resolution."""
    return _HUMAN_RESOLUTION_ADAPTER.validate_python(payload)


class GraphResumeRequest(BaseModel):
    """Payload for ``POST /api/v1/estimate/graph/{estimation_id}/resume``.

    Prefer ``resolution``. Legacy ``decision`` is accepted when it already
    carries a feature-067 ``action`` field (temporary adapter).
    """

    resolution: ApproveResolution | AdjustResolution | RejectResolution | None = None
    decision: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_resolution_or_compatible_decision(self) -> GraphResumeRequest:
        if self.resolution is not None:
            return self
        if self.decision.get("action") in {"approve", "adjust", "reject"}:
            return self
        raise ValueError(
            "Provide resolution={action: approve|adjust|reject, ...} "
            "(or a decision object with the same action field)."
        )

    def resolved_payload(self) -> dict[str, Any]:
        """Return the dict passed to ``Command(resume=...)``."""
        if self.resolution is not None:
            return self.resolution.model_dump()
        return dict(self.decision)


class PendingGate(BaseModel):
    """The human gate a paused run is waiting on (the ``interrupt`` payload)."""

    gate: str  # "estimation_review"
    estimation_id: str
    payload: dict = Field(default_factory=dict)


class GraphRunState(BaseModel):
    """Snapshot of a multi-agent run: paused at a gate, or completed.

    Returned by START, RESUME, and the read-only STATE endpoint.

    ``state`` is the checkpointer lifecycle (``paused`` | ``completed``).
    ``status`` is the business outcome
    (``awaiting_human_review`` | ``completed`` | ``rejected``).
    """

    estimation_id: str
    state: str  # "paused" | "completed"
    pending_gate: PendingGate | None = None
    requirements: list = Field(default_factory=list)
    budget_matches: list[dict] = Field(default_factory=list)
    estimate: dict | None = None
    validation: dict | None = None
    confidence: float | None = None
    status: str | None = None
    human_resolution: dict | None = None
    errors: list[str] = Field(default_factory=list)
    # Optional proposal artifact when drafted on demand / leftover state.
    proposal: str | None = None


class ActivityEntry(BaseModel):
    """One didactic line of what an agent just did (see ``activity.py``)."""

    seq: int = 0
    node: str
    label: str
    message: str
    ts: str | None = None


class GraphProgress(GraphRunState):
    """Live progress of a background-streamed run: ``GraphRunState`` + activity.

    ``state`` gains ``"running"`` — mid-leg while the panel fills.
    """

    state: Literal["running", "paused", "completed"]  # type: ignore[assignment]
    activity: list[ActivityEntry] = Field(default_factory=list)


class GraphProposalResponse(BaseModel):
    """Commercial proposal from ``POST …/graph/{id}/proposal``.

    Generated on demand over the run's estimate (no graph re-run).
    """

    estimation_id: str
    title: str
    executive_summary: str
    scope: list[str] = Field(default_factory=list)
    total_engineer_days: int | None = None
    body_markdown: str
