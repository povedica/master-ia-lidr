"""Integration test for session eval runner with fake structured LLM."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.sessions import InMemorySessionStore
from tests.evals.fakes import EvalStructuredLLM
from tests.evals.loader import get_case
from tests.evals.session_runner import SessionEvalRunner

pytest_plugins = ["tests.evals.conftest_eval"]


@pytest.mark.asyncio
@pytest.mark.evals
async def test_runner_replays_small_golden_case(
    eval_async_client: AsyncClient,
    eval_session_store: InMemorySessionStore,
    eval_structured_llm: EvalStructuredLLM,
) -> None:
    case = get_case("small-single-turn-web")
    outcome = await SessionEvalRunner().run_case(
        case,
        client=eval_async_client,
        store=eval_session_store,
        fake=eval_structured_llm,
    )

    assert outcome.case_id == "small-single-turn-web"
    assert outcome.final_estimate.totals.hours > 0
    assert outcome.project_metadata.project_name == "Portal Acme"
    assert len(outcome.turn_responses) == 1
    assert outcome.final_response.session_id == outcome.session_id
