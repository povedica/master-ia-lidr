"""Post-generation hallucination gate (numeric anchors + per-line grades).

Step 1: pure helpers. Step 2+: judge and service wiring.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from app.config import Settings
from app.schemas.hallucination_report import (
    HallucinationJudgeBatchResult,
    HallucinationJudgeLineResult,
    HallucinationLineGrade,
)
from app.schemas.rag_estimation_result import RagEstimationLineItem, RagEstimationResult
from app.services.llm_types import LLMProvider
from app.services.provider_routing import resolve_first_litellm_route
from app.services.structured_llm_client import StructuredCompletionError, complete_structured

logger = logging.getLogger(__name__)

_DEFAULT_TOLERANCE = 0.25
_JUDGE_MAX_OUTPUT_TOKENS = 1200

_HOUR_PATTERN = re.compile(
    r"(?i)\b(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b"
)

_JUDGE_SYSTEM = (
    "You audit software estimation line items for numeric hallucinations. "
    "Compare each line's claimed hours against numeric anchors extracted from "
    "retrieved budget chunks. Grade each line as grounded (supported by anchors), "
    "degraded (hours materially exceed anchors), or insufficient (cannot verify)."
)


def numeric_anchor(chunk_texts: Sequence[str]) -> list[float]:
    """Extract hour-like numeric values from chunk texts deterministically."""

    values: list[float] = []
    for text in chunk_texts:
        for match in _HOUR_PATTERN.finditer(text):
            values.append(float(match.group(1)))
    return sorted(values)


def gate_line(
    *,
    line_hours: float,
    anchor_hours: Sequence[float],
    tolerance: float = _DEFAULT_TOLERANCE,
) -> HallucinationLineGrade:
    """Grade one line by comparing claimed hours to numeric anchors."""

    if not anchor_hours:
        return HallucinationLineGrade.INSUFFICIENT

    anchor_max = max(anchor_hours)
    if anchor_max <= 0:
        return HallucinationLineGrade.INSUFFICIENT

    upper_bound = anchor_max * (1.0 + tolerance)
    if line_hours <= upper_bound:
        return HallucinationLineGrade.GROUNDED
    return HallucinationLineGrade.DEGRADED


def _build_judge_user_prompt(
    estimate: RagEstimationResult,
    *,
    anchors: Sequence[float],
    chunk_texts: Sequence[str],
) -> str:
    anchor_text = ", ".join(str(value) for value in anchors) if anchors else "(none)"
    chunk_blocks = "\n\n".join(
        f"Chunk {index + 1}:\n{text.strip()}"
        for index, text in enumerate(chunk_texts)
    )
    line_blocks = "\n\n".join(
        _format_line_for_judge(index, item)
        for index, item in enumerate(estimate.line_items)
    )
    return (
        f"Numeric anchors (hours): {anchor_text}\n\n"
        f"Retrieved chunks:\n{chunk_blocks}\n\n"
        f"Line items to judge:\n{line_blocks}"
    )


def _format_line_for_judge(index: int, item: RagEstimationLineItem) -> str:
    return (
        f"Line {index}: component={item.component!r}, "
        f"hours={item.hours}, rationale={item.rationale.strip()}"
    )


def _insufficient_for_all(line_count: int) -> list[HallucinationJudgeLineResult]:
    return [
        HallucinationJudgeLineResult(index=index, grade=HallucinationLineGrade.INSUFFICIENT)
        for index in range(line_count)
    ]


def _align_judge_results(
    raw: Sequence[HallucinationJudgeLineResult],
    *,
    line_count: int,
) -> list[HallucinationJudgeLineResult]:
    by_index = {line.index: line for line in raw}
    return [
        by_index.get(
            index,
            HallucinationJudgeLineResult(
                index=index,
                grade=HallucinationLineGrade.INSUFFICIENT,
            ),
        )
        for index in range(line_count)
    ]


async def judge_estimate(
    estimate: RagEstimationResult,
    *,
    chunk_texts: Sequence[str],
    settings: Settings,
    providers: list[LLMProvider],
    judge_model: str = "",
) -> list[HallucinationJudgeLineResult]:
    """Batch-judge line items against numeric anchors via structured LLM."""

    line_count = len(estimate.line_items)
    if line_count == 0:
        return []

    route = resolve_first_litellm_route(providers)
    if route is None:
        logger.warning(
            "hallucination_judge_no_provider",
            extra={"line_count": line_count},
        )
        return _insufficient_for_all(line_count)

    anchors = numeric_anchor(chunk_texts)
    litellm_model = judge_model.strip() or route.litellm_model
    user_prompt = _build_judge_user_prompt(
        estimate,
        anchors=anchors,
        chunk_texts=chunk_texts,
    )

    try:
        batch, _, _ = await complete_structured(
            litellm_model=litellm_model,
            chain_provider=route.provider_name,
            api_key=route.api_key,
            timeout_seconds=route.timeout_seconds,
            system_prompt=_JUDGE_SYSTEM,
            user_prompt=user_prompt,
            max_output_tokens=_JUDGE_MAX_OUTPUT_TOKENS,
            response_model=HallucinationJudgeBatchResult,
            max_attempts=settings.structured_output_max_attempts,
        )
    except StructuredCompletionError as exc:
        logger.warning(
            "hallucination_judge_failed",
            extra={
                "line_count": line_count,
                "error_type": type(exc).__name__,
            },
        )
        return _insufficient_for_all(line_count)

    return _align_judge_results(batch.lines, line_count=line_count)
