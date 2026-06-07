"""LLM-as-judge session quality tests (live estimator + live judge)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.sessions import InMemorySessionStore
from tests.evals.artifacts import write_judge_failure_artifact
from tests.evals.eval_markers import requires_judge_credentials, requires_live_estimator
from tests.evals.fakes import EvalStructuredLLM
from tests.evals.judge.config import configure_judge_env, judge_threshold_mode, resolve_judge_config
from tests.evals.judge.runner import evaluate_session_with_judge
from tests.evals.loader import list_cases
from tests.evals.models import GoldenSessionCase
from tests.evals.serialization import build_judge_context_block
from tests.evals.session_runner import SessionEvalRunner

pytest_plugins = ["tests.evals.conftest_eval"]

_CASES = list_cases()


@pytest.mark.asyncio
@pytest.mark.evals
@pytest.mark.slow
@pytest.mark.judge
@requires_live_estimator
@requires_judge_credentials
@pytest.mark.parametrize("case", _CASES, ids=[case.case_id for case in _CASES])
async def test_judge_session_quality(
    case: GoldenSessionCase,
    eval_async_client: AsyncClient,
    eval_session_store: InMemorySessionStore,
    eval_structured_llm: EvalStructuredLLM,
) -> None:
    config = resolve_judge_config()
    configure_judge_env(config)

    outcome = await SessionEvalRunner().run_case(
        case,
        client=eval_async_client,
        store=eval_session_store,
        fake=None,
    )
    results = evaluate_session_with_judge(case, outcome, config)
    scores = {item.name: item.score for item in results}
    failures = [item for item in results if not item.success]

    if failures:
        context_block = build_judge_context_block(case, outcome)
        write_judge_failure_artifact(
            case_id=case.case_id,
            scores=scores,
            context_block=context_block,
            extra={"failed_metrics": [item.name for item in failures]},
        )

    if judge_threshold_mode() == "strict":
        assert not failures, f"judge failures for {case.case_id}: {scores}"
    # warn mode: sub-threshold scores are recorded in artifacts but do not fail the test
