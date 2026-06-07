"""Build judge input/context strings from session eval outcomes."""

from __future__ import annotations

import json
from typing import Any

from app.schemas.estimation_result import EstimationResult
from app.services.sessions import DerivedProjectMetadata, ProjectMetadata
from tests.evals.models import GoldenSessionCase, SuccessCriteria
from tests.evals.session_runner import SessionEvalOutcome


def build_prior_turns_input(case: GoldenSessionCase) -> str:
    """Concatenate user transcripts from turns before the eval turn."""

    lines: list[str] = []
    for index, turn in enumerate(case.turns):
        if index >= case.eval_turn_index:
            break
        excerpt = turn.submit.transcript.strip()[:800]
        lines.append(f"[Turn {index + 1} — {turn.label}]\n{excerpt}")
    if not lines and case.turns:
        eval_turn = case.turns[case.eval_turn_index]
        excerpt = eval_turn.submit.transcript.strip()[:800]
        lines.append(f"[Eval turn — {eval_turn.label}]\n{excerpt}")
    return "\n\n".join(lines)


def serialize_estimation_result(estimate: EstimationResult) -> str:
    payload = estimate.model_dump(mode="json")
    compact = {
        "title": payload.get("title"),
        "summary": payload.get("summary"),
        "phases": payload.get("phases"),
        "line_items": payload.get("line_items"),
        "totals": payload.get("totals"),
        "duration_weeks": payload.get("duration_weeks"),
        "confidence": payload.get("confidence"),
        "assumptions": payload.get("assumptions"),
        "risks": payload.get("risks"),
    }
    return json.dumps(compact, ensure_ascii=False, indent=2)


def serialize_metadata_block(
    *,
    derived: DerivedProjectMetadata,
    session_metadata: ProjectMetadata | None,
) -> str:
    block: dict[str, Any] = {
        "derived_project_metadata": derived.model_dump(mode="json"),
    }
    if session_metadata is not None:
        block["session_project_metadata"] = session_metadata.model_dump(mode="json")
    return json.dumps(block, ensure_ascii=False, indent=2)


def serialize_success_criteria_summary(criteria: SuccessCriteria) -> str:
    summary: dict[str, Any] = {}
    if criteria.expected_hours_range is not None:
        summary["expected_hours_range"] = list(criteria.expected_hours_range)
    if criteria.expected_components:
        summary["expected_components"] = criteria.expected_components
    if criteria.expected_risks:
        summary["expected_risks"] = criteria.expected_risks
    if criteria.hard_constraints.must_not_mention:
        summary["must_not_mention"] = criteria.hard_constraints.must_not_mention
    return json.dumps(summary, ensure_ascii=False, indent=2)


def build_judge_context_block(
    case: GoldenSessionCase,
    outcome: SessionEvalOutcome,
) -> str:
    """Single structured context block for GEval metrics."""

    return "\n\n".join(
        [
            "## Session context (prior turns)",
            build_prior_turns_input(case),
            "## Accumulated project metadata",
            serialize_metadata_block(
                derived=outcome.project_metadata,
                session_metadata=outcome.session_metadata,
            ),
            "## Final structured estimate",
            serialize_estimation_result(outcome.final_estimate),
            "## Golden success criteria (for calibration)",
            serialize_success_criteria_summary(case.success_criteria),
            "## Domain notes for judge",
            case.notes_for_judge.strip(),
        ]
    )
