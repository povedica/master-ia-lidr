"""Soft consistency eval tests (live estimator, multi-run)."""

from __future__ import annotations

import os
import statistics

import pytest
from httpx import AsyncClient

from app.services.sessions import InMemorySessionStore
from tests.evals.assertions import _component_present, _normalized_token
from tests.evals.eval_markers import requires_live_estimator
from tests.evals.fakes import EvalStructuredLLM
from tests.evals.loader import get_case
from tests.evals.session_runner import SessionEvalRunner
from tests.evals import thresholds as t

pytest_plugins = ["tests.evals.conftest_eval"]

_SOFT_CASE_IDS = ("medium-redis-second-turn", "ambiguous-clarified")


def _soft_run_count() -> int:
    raw = os.getenv("EVAL_SOFT_CONSISTENCY_RUNS", str(t.SOFT_CONSISTENCY_RUNS)).strip()
    return max(2, int(raw))


@pytest.mark.asyncio
@pytest.mark.evals
@pytest.mark.slow
@pytest.mark.soft
@requires_live_estimator
@pytest.mark.parametrize("case_id", _SOFT_CASE_IDS)
async def test_soft_consistency_multi_run(
    case_id: str,
    eval_async_client: AsyncClient,
    eval_session_store: InMemorySessionStore,
    eval_structured_llm: EvalStructuredLLM,
) -> None:
    case = get_case(case_id)
    runs = _soft_run_count()
    hours_samples: list[float] = []
    confidence_samples: list[float] = []
    component_hits = 0

    for _ in range(runs):
        outcome = await SessionEvalRunner().run_case(
            case,
            client=eval_async_client,
            store=eval_session_store,
            fake=None,
        )
        hours_samples.append(outcome.final_estimate.totals.hours)
        confidence_samples.append(outcome.final_estimate.confidence)
        if all(_component_present(component, outcome.final_estimate) for component in case.success_criteria.expected_components):
            component_hits += 1
        eval_session_store.reset_for_tests()

    median_hours = statistics.median(hours_samples)
    allowed_delta = median_hours * t.SOFT_HOURS_VARIANCE_RATIO
    for hours in hours_samples:
        assert abs(hours - median_hours) <= allowed_delta, f"hours {hours} deviates >15% from median {median_hours}"

    min_hits = int(runs * t.SOFT_COMPONENT_MIN_RUNS_RATIO + 0.999)
    assert component_hits >= min_hits, f"components present in only {component_hits}/{runs} runs"

    median_conf = statistics.median(confidence_samples)
    for conf in confidence_samples:
        assert abs(conf - median_conf) <= t.SOFT_CONFIDENCE_DELTA
