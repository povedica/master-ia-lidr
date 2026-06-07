"""Unit tests for per-turn stress observation builder."""

from __future__ import annotations

from app.guardrails.contracts import FinalResponseStatus
from app.guardrails.llm_pipeline import StructuredPipelineOutcome
from app.schemas.estimation_request import ProjectType, TargetAudience
from app.schemas.estimation_result import EstimationLineItem, EstimationResult, EstimationTotals
from app.services.llm_service import StructuredEstimateBundle, UsageInfo
from app.services.sessions import (
    ConversationHistory,
    DerivedProjectMetadata,
    ProjectMetadata,
    Session,
)
from app.services.turn_observation import TURN_OBSERVED_FIELDS, build_turn_observation


def _session_with_history() -> Session:
    session = Session(session_id="sess-abc")
    session.submit_count = 1
    session.conversation_history = ConversationHistory(max_turns=10)
    session.conversation_history.set_system_prompt("system prompt")
    session.conversation_history.add_user_message("[Turn 1] first user")
    session.conversation_history.add_assistant_message("first assistant")
    session.project_metadata = ProjectMetadata(
        project_name="Nimbus",
        agreed_scope="Scope for Nimbus includes auth and audit log.",
        explicit_constraints=["budget locked: 30000 EUR"],
    )
    session.last_derived_metadata = DerivedProjectMetadata(
        project_name="Nimbus",
        project_type=ProjectType.web_saas,
        target_audience=TargetAudience.b2b_enterprise,
        summary="Scope for Nimbus includes auth and audit log.",
        detected_constraints=["budget locked: 30000 EUR"],
    )
    return session


def _bundle_with_usage() -> StructuredEstimateBundle:
    li = EstimationLineItem(name="Auth module", hours=40.0, cost_eur=2000.0)
    totals = EstimationTotals(hours=120.0, cost_eur=6000.0)
    result = EstimationResult(
        title="Nimbus MVP",
        summary="Initial estimate for Nimbus platform.",
        line_items=[li],
        totals=totals,
        duration_weeks=8.0,
        confidence=0.82,
    )
    return StructuredEstimateBundle(
        result=result,
        prompt_version="v1",
        examples_version="v1",
        model="gpt-4o-mini",
        provider="openai",
        usage=UsageInfo(prompt_tokens=1500, completion_tokens=220, total_tokens=1720),
        degraded=False,
        finish_reason="stop",
    )


def test_build_turn_observation_includes_all_required_fields() -> None:
    session = _session_with_history()
    pipeline = StructuredPipelineOutcome(
        bundle=_bundle_with_usage(),
        cached=True,
        cache_score=0.92,
        cache_bucket="semantic",
        final_status=FinalResponseStatus.SUCCESS,
        reason_code=None,
        user_message=None,
        technical_message=None,
        audit_id="audit-1",
        safe_to_cache=True,
        safe_to_display=True,
        cache_miss_reason=None,
        acb_trace=None,
    )

    observation = build_turn_observation(
        session=session,
        pipeline=pipeline,
        enriched_transcript_chars=4200,
        attachments_total_chars=5120,
        latency_ms=1850,
    )

    assert set(observation.keys()) == set(TURN_OBSERVED_FIELDS)
    assert observation["turn_index"] == 1
    assert observation["session_id"] == "sess-abc"
    assert observation["enriched_transcript_chars"] == 4200
    assert observation["attachments_total_chars"] == 5120
    assert observation["messages_in_window"] == 2
    assert observation["anchors_count"] == 0
    assert observation["summary_chars"] == len(session.project_metadata.agreed_scope or "")
    assert observation["tokens_in"] == 1500
    assert observation["tokens_out"] == 220
    assert observation["cost_usd"] is not None
    assert observation["latency_ms"] == 1850
    assert observation["cache_hit_kind"] == "semantic"
    assert observation["last_resolved_tier"] == "default"


def test_build_turn_observation_uses_none_defaults_when_usage_missing() -> None:
    session = _session_with_history()
    pipeline = StructuredPipelineOutcome(
        bundle=None,
        cached=False,
        cache_score=None,
        cache_bucket=None,
        final_status=FinalResponseStatus.ERROR,
        reason_code="provider_error",
        user_message="failed",
        technical_message="failed",
        audit_id="audit-2",
        safe_to_cache=False,
        safe_to_display=False,
        cache_miss_reason="error",
        acb_trace=None,
    )

    observation = build_turn_observation(
        session=session,
        pipeline=pipeline,
        enriched_transcript_chars=900,
        attachments_total_chars=0,
        latency_ms=50,
        usage_model="gpt-4o-mini",
        usage=None,
    )

    assert observation["tokens_in"] is None
    assert observation["tokens_out"] is None
    assert observation["cost_usd"] is None
    assert observation["cache_hit_kind"] == "none"
