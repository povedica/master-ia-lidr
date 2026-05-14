"""Apply registry-backed policies to individual ``GuardrailResult`` rows."""

from __future__ import annotations

import logging
from time import perf_counter

from app.config import Settings
from app.guardrails.audit import log_guardrail_event
from app.guardrails.contracts import (
    GuardrailPolicy,
    GuardrailResult,
    PolicyOutcome,
    PolicyOutcomeStatus,
    RolloutMode,
)
from app.guardrails.policy_registry import guardrail_declaration_by_id
from app.guardrails.rollout_resolution import effective_rollout

logger = logging.getLogger(__name__)


class PolicyExecutor:
    """Translate guardrail results + registry metadata into ``PolicyOutcome``."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def apply(self, result: GuardrailResult, *, audit_id: str) -> PolicyOutcome:
        started = perf_counter()
        decl = guardrail_declaration_by_id(result.guardrail_id)
        if decl is None:
            latency_ms = int((perf_counter() - started) * 1000)
            log_guardrail_event(
                "guardrail_policy_unknown_id",
                audit_id=audit_id,
                guardrail_id=result.guardrail_id,
                layer=result.layer.value,
                passed=result.passed,
                rollout="unknown",
                reason_code="unknown_guardrail_id",
                latency_ms=latency_ms,
            )
            return PolicyOutcome(
                guardrail_id=result.guardrail_id,
                policy=result.recommended_policy,
                status=PolicyOutcomeStatus.NONE,
                reason_code="unknown_guardrail_id",
                audit_payload={"note": "missing_registry_declaration"},
            )

        rollout = effective_rollout(decl, self._settings)
        policy = decl.on_fail
        latency_ms = int((perf_counter() - started) * 1000)

        if rollout == RolloutMode.DISABLED:
            return PolicyOutcome(
                guardrail_id=result.guardrail_id,
                policy=policy,
                status=PolicyOutcomeStatus.NONE,
                reason_code="rollout_disabled",
                audit_payload={"registry_rollout": decl.rollout.value},
            )

        if result.passed:
            log_guardrail_event(
                "guardrail_passed",
                audit_id=audit_id,
                guardrail_id=result.guardrail_id,
                layer=result.layer.value,
                passed=True,
                rollout=rollout.value,
                latency_ms=latency_ms,
            )
            return PolicyOutcome(
                guardrail_id=result.guardrail_id,
                policy=policy,
                status=PolicyOutcomeStatus.NONE,
                reason_code="passed",
                audit_payload={},
            )

        if rollout == RolloutMode.LOG_ONLY:
            if decl.metrics_event_name:
                logger.info(
                    "guardrail_metric",
                    extra={
                        "metric": decl.metrics_event_name,
                        "would_block": True,
                        "audit_id": audit_id,
                        "rollout": rollout.value,
                    },
                )
            log_guardrail_event(
                "guardrail_log_only",
                audit_id=audit_id,
                guardrail_id=result.guardrail_id,
                layer=result.layer.value,
                passed=False,
                rollout=rollout.value,
                policy=policy.value,
                reason_code="would_have_blocked",
                latency_ms=latency_ms,
            )
            return PolicyOutcome(
                guardrail_id=result.guardrail_id,
                policy=policy,
                status=PolicyOutcomeStatus.RECORDED_LOG_ONLY,
                reason_code="would_have_blocked",
                audit_payload={"reasons": ",".join(result.reasons[:5])},
            )

        if decl.metrics_event_name:
            logger.info(
                "guardrail_metric",
                extra={
                    "metric": decl.metrics_event_name,
                    "blocked": True,
                    "audit_id": audit_id,
                },
            )
        log_guardrail_event(
            "guardrail_enforced",
            audit_id=audit_id,
            guardrail_id=result.guardrail_id,
            layer=result.layer.value,
            passed=False,
            rollout=rollout.value,
            policy=policy.value,
            reason_code="enforced",
            latency_ms=latency_ms,
        )
        return PolicyOutcome(
            guardrail_id=result.guardrail_id,
            policy=policy,
            status=PolicyOutcomeStatus.ENFORCED,
            reason_code="enforced",
            retry_allowed=policy == GuardrailPolicy.FIX_RETRY,
            retry_after_fix=policy == GuardrailPolicy.FIX_RETRY,
            audit_payload={"reasons": ",".join(result.reasons[:5])},
        )
