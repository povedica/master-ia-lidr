"""Run GEval metrics for a session eval outcome."""

from __future__ import annotations

from dataclasses import dataclass

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase

from tests.evals.judge.config import JudgeConfig
from tests.evals.judge.metrics import build_session_eval_metrics
from tests.evals.models import GoldenSessionCase
from tests.evals.serialization import build_judge_context_block, build_prior_turns_input, serialize_estimation_result
from tests.evals.session_runner import SessionEvalOutcome


@dataclass(frozen=True)
class JudgeMetricResult:
    name: str
    score: float | None
    success: bool
    reason: str | None


def build_llm_test_case(case: GoldenSessionCase, outcome: SessionEvalOutcome) -> LLMTestCase:
    return LLMTestCase(
        input=build_prior_turns_input(case),
        actual_output=serialize_estimation_result(outcome.final_estimate),
        context=[build_judge_context_block(case, outcome)],
    )


def evaluate_session_with_judge(
    case: GoldenSessionCase,
    outcome: SessionEvalOutcome,
    config: JudgeConfig,
) -> list[JudgeMetricResult]:
    test_case = build_llm_test_case(case, outcome)
    results: list[JudgeMetricResult] = []
    for metric in build_session_eval_metrics(config):
        score = _measure_metric(metric, test_case)
        success = metric.is_successful() if score is not None else False
        results.append(
            JudgeMetricResult(
                name=metric.name,
                score=score,
                success=success,
                reason=getattr(metric, "reason", None),
            )
        )
    return results


def _measure_metric(metric: GEval, test_case: LLMTestCase) -> float | None:
    try:
        return metric.measure(test_case, _show_indicator=False, _log_metric_to_confident=False)
    except Exception:
        return None
