"""ACB orchestration run context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.schemas.estimation_request import EstimationRequest


@dataclass(frozen=True)
class AcbRunContext:
    """Pre-built session estimation inputs for one ACB run."""

    request: EstimationRequest
    assessment_surface: str
    project_metadata: dict[str, Any] = field(default_factory=dict)
    system_prompt_override: str | None = None
    user_prompt_override: str | None = None
    messages_override: list[dict[str, str]] | None = None
    skip_domain_guardrail: bool = True
