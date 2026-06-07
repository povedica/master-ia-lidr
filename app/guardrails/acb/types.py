"""ACB orchestration outcome types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.schemas.acb.trace import AcbFinalPath, AcbTrace
from app.schemas.estimation_result import EstimationResult
from app.services.llm_service import StructuredEstimateBundle

AcbOrchestrationFinalPath = Literal[
    "accept",
    "revise_exhausted_synthesize",
    "synthesize",
    "accept_on_budget_exhausted",
    "accept_fallback",
]


@dataclass(frozen=True)
class AcbOrchestrationOutcome:
    """Final structured result plus trace metadata from one ACB run."""

    bundle: StructuredEstimateBundle
    trace: AcbTrace
    final_path: AcbFinalPath
    final_result: EstimationResult
