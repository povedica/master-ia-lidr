"""Unit tests for judge serialization helpers."""

from __future__ import annotations

from app.services.sessions import DerivedProjectMetadata
from tests.evals.fakes import build_estimation_from_criteria
from tests.evals.loader import get_case
from tests.evals.serialization import (
    build_judge_context_block,
    build_prior_turns_input,
    serialize_estimation_result,
)
from tests.evals.session_runner import SessionEvalOutcome


def test_build_prior_turns_input_includes_turn_one_for_multi_turn_case() -> None:
    case = get_case("medium-redis-second-turn")
    text = build_prior_turns_input(case)
    assert "Turn 1" in text
    assert "Acme Corp" in text


def test_serialize_estimation_result_is_compact_json_without_secrets() -> None:
    case = get_case("small-single-turn-web")
    estimate = build_estimation_from_criteria(case.success_criteria)
    payload = serialize_estimation_result(estimate)
    assert '"title"' in payload
    assert '"totals"' in payload
    assert "api_key" not in payload.lower()
    assert "secret" not in payload.lower()


def test_build_judge_context_block_includes_required_sections() -> None:
    case = get_case("small-single-turn-web")
    estimate = build_estimation_from_criteria(case.success_criteria)
    outcome = SessionEvalOutcome(
        case_id=case.case_id,
        session_id="test-session",
        final_response=None,  # type: ignore[arg-type]
        final_estimate=estimate,
        project_metadata=DerivedProjectMetadata(
            project_name="Portal Acme",
            project_type="web_saas",
            target_audience="b2b_smb",
        ),
        session_metadata=None,
        conversation_snippet=[],
        turn_responses=[],
        warnings=[],
    )
    block = build_judge_context_block(case, outcome)
    assert "## Session context" in block
    assert "## Accumulated project metadata" in block
    assert "## Final structured estimate" in block
    assert "## Golden success criteria" in block
    assert case.notes_for_judge.strip()[:20] in block
