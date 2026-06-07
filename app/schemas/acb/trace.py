"""ACB orchestration trace metadata schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.acb.boss import BossAction
from app.services.llm_types import UsageInfo

AcbFinalPath = Literal[
    "accept",
    "revise_exhausted_synthesize",
    "synthesize",
    "accept_on_budget_exhausted",
    "accept_fallback",
]


class AcbIterationRecord(BaseModel):
    """Per-iteration observability record."""

    model_config = ConfigDict(extra="forbid")

    iteration: int = Field(..., ge=1)
    boss_action: BossAction
    critic_issue_counts: dict[str, int]
    actor_model: str = Field(..., min_length=1, max_length=128)
    critic_model: str = Field(..., min_length=1, max_length=128)
    boss_model: str = Field(..., min_length=1, max_length=128)
    timings_ms: dict[str, int]
    usage: UsageInfo | None = None


class AcbTrace(BaseModel):
    """Compact orchestration trace for logs and dev diagnostics."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    iterations: list[AcbIterationRecord]
    final_path: AcbFinalPath
    total_usage: UsageInfo | None = None
    prompt_version_acb: str = Field(..., min_length=1, max_length=32)
