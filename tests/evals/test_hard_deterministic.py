"""Hard deterministic eval tests over golden session cases (fake LLM)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.sessions import InMemorySessionStore
from tests.evals.assertions import assert_hard_deterministic_outcome
from tests.evals.fakes import EvalStructuredLLM
from tests.evals.loader import list_cases
from tests.evals.models import GoldenSessionCase
from tests.evals.session_runner import SessionEvalRunner

pytest_plugins = ["tests.evals.conftest_eval"]

_CASES = list_cases()


@pytest.mark.asyncio
@pytest.mark.evals
@pytest.mark.parametrize("case", _CASES, ids=[case.case_id for case in _CASES])
async def test_hard_deterministic_golden_case(
    case: GoldenSessionCase,
    eval_async_client: AsyncClient,
    eval_session_store: InMemorySessionStore,
    eval_structured_llm: EvalStructuredLLM,
) -> None:
    outcome = await SessionEvalRunner().run_case(
        case,
        client=eval_async_client,
        store=eval_session_store,
        fake=eval_structured_llm,
    )
    assert_hard_deterministic_outcome(case, outcome)
