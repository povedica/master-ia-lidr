"""Build ``EstimateResponse`` objects shared by HTTP API and internal UIs."""

from __future__ import annotations

import json
from datetime import datetime

from app.schemas.estimations import (
    EstimateResponse,
    StructureCheckView,
    UsageView,
)
from app.services.evaluation import StructureCheck, evaluate_estimation_structure
from app.services.llm_service import PROMPT_VERSION, EXAMPLES_VERSION, LlmEstimationCallOutcome


_MODEL_COSTS_PER_1M_TOKENS: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
}


def estimate_cost_usd(model: str, usage: UsageView | None) -> float | None:
    """Estimate request cost in USD when token pricing is known."""

    if usage is None:
        return None
    prices = _MODEL_COSTS_PER_1M_TOKENS.get(model)
    if prices is None:
        return None
    input_price, output_price = prices
    cost = (
        (usage.prompt_tokens / 1_000_000) * input_price
        + (usage.completion_tokens / 1_000_000) * output_price
    )
    return round(cost, 8)


def assemble_estimate_response(
    result: LlmEstimationCallOutcome,
    *,
    evaluate: bool,
    dev_mode: bool,
    stats_log_enabled: bool,
    request_id: str,
    finished_at: datetime,
    latency_ms: int,
) -> tuple[EstimateResponse, StructureCheck | None]:
    """Compose the outbound payload exactly as ``POST /api/v1/estimate`` does.

    Returns ``structure_check`` for stats logging even when evaluation fields are omitted
    from the JSON body (evaluate=false with stats-only runs).
    """

    degraded_value = True if result.degraded else None

    structure_evaluation: StructureCheckView | None = None
    structure_check = None
    if evaluate or stats_log_enabled:
        finish = (result.finish_reason or "").strip() or "stop"
        structure_check = evaluate_estimation_structure(result.estimation, finish)
    if evaluate and structure_check is not None:
        structure_evaluation = StructureCheckView(
            has_title=structure_check.has_title,
            has_breakdown_table=structure_check.has_breakdown_table,
            has_totals_section=structure_check.has_totals_section,
            has_team_section=structure_check.has_team_section,
            has_duration_section=structure_check.has_duration_section,
            declared_total_hours=structure_check.declared_total_hours,
            sum_row_hours=structure_check.sum_row_hours,
            hours_match=structure_check.hours_match,
            declared_total_cost=structure_check.declared_total_cost,
            sum_row_cost=structure_check.sum_row_cost,
            cost_match=structure_check.cost_match,
            finish_reason_ok=structure_check.finish_reason_ok,
            score=structure_check.score,
            issues=list(structure_check.issues),
        )

    response_score = structure_check.score if evaluate and structure_check else None

    if not dev_mode:
        return (
            EstimateResponse(
                estimation=result.estimation,
                score=response_score,
                degraded=degraded_value,
                structure_evaluation=structure_evaluation,
            ),
            structure_check,
        )

    usage: UsageView | None = None
    if result.usage:
        usage = UsageView(
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            total_tokens=result.usage.total_tokens,
            preprocessing_input_tokens=result.usage.preprocessing_input_tokens,
            preprocessing_output_tokens=result.usage.preprocessing_output_tokens,
        )
        usage.estimated_cost_usd = estimate_cost_usd(result.model, usage)

    return (
        EstimateResponse(
            estimation=result.estimation,
            score=response_score,
            model=result.model,
            provider=result.provider,
            request_id=request_id,
            timestamp=finished_at,
            latency_ms=latency_ms,
            prompt_version=PROMPT_VERSION,
            examples_version=EXAMPLES_VERSION,
            degraded=degraded_value,
            usage=usage,
            finish_reason=result.finish_reason,
            structure_evaluation=structure_evaluation,
        ),
        structure_check,
    )


def dev_response_property_rows(response: EstimateResponse) -> list[dict[str, str]]:
    """Two-column rows for documenting or previewing JSON fields (DEV_MODE payloads)."""

    dumped = response.model_dump(mode="json", exclude_none=True)
    rows: list[dict[str, str]] = []
    estimation_limit = 2000
    for key in sorted(dumped.keys()):
        val = dumped[key]
        if isinstance(val, (dict, list)):
            text = json.dumps(val, ensure_ascii=False, indent=2)
        else:
            text = "" if val is None else str(val)
        if key == "estimation" and len(text) > estimation_limit:
            text = text[:estimation_limit] + "\n… (truncated for table view)"
        rows.append({"field": key, "value": text})
    return rows
