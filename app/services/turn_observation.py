"""Build per-turn stress observations for session estimate submits."""

from __future__ import annotations

from typing import Any

from app.guardrails.llm_pipeline import StructuredPipelineOutcome
from app.schemas.estimations import UsageView
from app.services.estimate_response_builder import estimate_cost_usd
from app.services.llm_service import StructuredEstimateBundle, UsageInfo
from app.services.sessions import Session

TURN_OBSERVED_FIELDS: tuple[str, ...] = (
    "turn_index",
    "session_id",
    "enriched_transcript_chars",
    "attachments_total_chars",
    "messages_in_window",
    "anchors_count",
    "summary_chars",
    "tokens_in",
    "tokens_out",
    "cost_usd",
    "latency_ms",
    "cache_hit_kind",
    "last_resolved_tier",
)


def build_turn_observation(
    *,
    session: Session,
    pipeline: StructuredPipelineOutcome,
    enriched_transcript_chars: int,
    attachments_total_chars: int,
    latency_ms: int,
    usage_model: str | None = None,
    usage: UsageInfo | None = None,
) -> dict[str, Any]:
    """Assemble the 13-field ``turn_observed`` payload for logging and debug retrieval."""

    bundle = pipeline.bundle
    resolved_usage = usage
    resolved_model = usage_model
    if bundle is not None:
        resolved_usage = bundle.usage
        resolved_model = bundle.model

    tokens_in = resolved_usage.prompt_tokens if resolved_usage is not None else None
    tokens_out = resolved_usage.completion_tokens if resolved_usage is not None else None
    cost_usd: float | None = None
    if resolved_usage is not None and resolved_model is not None:
        cost_usd = estimate_cost_usd(
            resolved_model,
            UsageView(
                prompt_tokens=resolved_usage.prompt_tokens,
                completion_tokens=resolved_usage.completion_tokens,
                total_tokens=resolved_usage.total_tokens,
            ),
        )

    summary_text = session.project_metadata.agreed_scope or ""
    if not summary_text and session.last_derived_metadata is not None:
        summary_text = session.last_derived_metadata.summary or ""

    return {
        "turn_index": session.submit_count,
        "session_id": session.session_id,
        "enriched_transcript_chars": enriched_transcript_chars,
        "attachments_total_chars": attachments_total_chars,
        "messages_in_window": _count_non_system_messages(session),
        "anchors_count": 0,
        "summary_chars": len(summary_text),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
        "latency_ms": latency_ms,
        "cache_hit_kind": "semantic" if pipeline.cached else "none",
        "last_resolved_tier": "default",
    }


def _count_non_system_messages(session: Session) -> int:
    return sum(
        1
        for message in session.conversation_history.to_messages_list()
        if message["role"] != "system"
    )


def observation_from_bundle(
    *,
    session: Session,
    pipeline: StructuredPipelineOutcome,
    enriched_transcript_chars: int,
    attachments_total_chars: int,
    latency_ms: int,
) -> dict[str, Any]:
    """Convenience wrapper when usage is taken from the pipeline bundle."""

    return build_turn_observation(
        session=session,
        pipeline=pipeline,
        enriched_transcript_chars=enriched_transcript_chars,
        attachments_total_chars=attachments_total_chars,
        latency_ms=latency_ms,
    )
