"""HTTP replay runner for multi-turn session golden cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from httpx import AsyncClient

from app.schemas.estimation_result import EstimationResult
from app.schemas.simplified_session import SessionEstimateResponse
from app.services.sessions import DerivedProjectMetadata, InMemorySessionStore, ProjectMetadata
from tests.evals.fakes import EvalStructuredLLM
from tests.evals.models import GoldenSessionCase
from tests.fixtures.session_store import get_session_state


@dataclass(frozen=True)
class SessionEvalOutcome:
    case_id: str
    session_id: str
    final_response: SessionEstimateResponse
    final_estimate: EstimationResult
    project_metadata: DerivedProjectMetadata
    session_metadata: ProjectMetadata | None
    conversation_snippet: list[dict[str, str]]
    turn_responses: list[dict[str, Any]]
    warnings: list[str]


class SessionEvalRunner:
    """Replay golden turns against the session estimate HTTP surface."""

    async def run_case(
        self,
        case: GoldenSessionCase,
        *,
        client: AsyncClient,
        store: InMemorySessionStore,
        fake: EvalStructuredLLM | None = None,
    ) -> SessionEvalOutcome:
        if fake is not None:
            fake.set_success_criteria(case.success_criteria)

        created = await client.post("/api/v1/sessions")
        if created.status_code != 201:
            raise RuntimeError(f"session create failed: {created.status_code} {created.text}")
        session_id = created.json()["session_id"]

        turn_responses: list[dict[str, Any]] = []
        for index, turn in enumerate(case.turns):
            if turn.skip_estimate:
                continue
            response = await client.post(
                f"/api/v1/sessions/{session_id}/estimate",
                json=turn.submit.model_dump(mode="json", exclude_none=True),
            )
            assert response.status_code == turn.expect_status, (
                f"turn {index} ({turn.label}): expected {turn.expect_status}, "
                f"got {response.status_code}: {response.text}"
            )
            turn_responses.append(response.json())

        final_json = turn_responses[case.eval_turn_index]
        final_response = SessionEstimateResponse.model_validate(final_json)
        final_estimate = _extract_estimation_result(final_json["estimate"])
        session = get_session_state(store, session_id)
        snippet = _conversation_snippet(session.conversation_history.to_messages_list())

        if fake is not None:
            fake.clear_success_criteria()

        return SessionEvalOutcome(
            case_id=case.case_id,
            session_id=session_id,
            final_response=final_response,
            final_estimate=final_estimate,
            project_metadata=final_response.project_metadata,
            session_metadata=session.project_metadata,
            conversation_snippet=snippet,
            turn_responses=turn_responses,
            warnings=list(final_response.warnings),
        )


def _extract_estimation_result(estimate_payload: dict[str, Any]) -> EstimationResult:
    result_data = estimate_payload.get("result", estimate_payload)
    return EstimationResult.model_validate(result_data)


def _conversation_snippet(messages: list[dict[str, str]], *, max_turns: int = 6) -> list[dict[str, str]]:
    non_system = [message for message in messages if message.get("role") != "system"]
    return non_system[-max_turns * 2 :]
