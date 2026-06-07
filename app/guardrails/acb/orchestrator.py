"""Actor-Critic-Boss orchestration loop."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.guardrails.acb.context import AcbRunContext
from app.guardrails.acb.policy import (
    actor_budget_remaining,
    count_issues_by_category,
    count_issues_by_severity,
    normalize_boss_decision,
    should_continue_loop,
)
from app.guardrails.acb.types import AcbOrchestrationOutcome
from app.schemas.acb.boss import BossAction, BossDecision
from app.schemas.acb.critic import CriticFeedback
from app.schemas.acb.trace import AcbFinalPath, AcbIterationRecord, AcbTrace
from app.schemas.estimation_result import EstimationResult
from app.services.acb_prompt_rendering import (
    ACB_PROMPT_VERSION,
    render_acb_actor_prompts,
    render_acb_boss_prompts,
    render_acb_critic_prompts,
)
from app.services.llm_service import EstimationService, StructuredEstimateBundle
from app.services.llm_types import UsageInfo
from app.services.observability.bootstrap import get_observability
from app.services.structured_llm_client import StructuredCompletionError, complete_structured

logger = logging.getLogger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)

StructuredCompleteFn = Callable[..., Awaitable[tuple[Any, UsageInfo | None, str | None]]]


class ActorCriticBossOrchestrator:
    """Runs Actor → Critic → Boss iterations until accept, synthesize, or budget stop."""

    def __init__(
        self,
        estimation_service: EstimationService,
        settings: Settings,
        *,
        structured_complete: StructuredCompleteFn | None = None,
    ) -> None:
        self._estimation = estimation_service
        self._settings = settings
        self._structured_complete = structured_complete or complete_structured

    async def run(
        self,
        ctx: AcbRunContext,
        *,
        max_iterations: int | None = None,
        allow_synthesize: bool | None = None,
        blocking_severities: frozenset[str] | None = None,
        critic_model: str | None = None,
        boss_model: str | None = None,
    ) -> AcbOrchestrationOutcome:
        max_iter = max_iterations if max_iterations is not None else self._settings.acb_max_iterations
        allow_syn = (
            allow_synthesize if allow_synthesize is not None else self._settings.acb_allow_synthesize
        )
        blocking = blocking_severities or self._settings.acb_blocking_severities_set()

        logger.info(
            "acb_orchestration_started",
            extra={"max_iterations": max_iter, "allow_synthesize": allow_syn},
        )

        observability = get_observability()
        observability.add_tags("feature:session_estimate", "orchestration:acb")

        with observability.start_span(
            "acb_orchestration",
            attributes={
                "max_iterations": max_iter,
                "allow_synthesize": allow_syn,
                "prompt_version_acb": ACB_PROMPT_VERSION,
            },
        ):
            return await self._run_iterations(
                ctx=ctx,
                max_iter=max_iter,
                allow_syn=allow_syn,
                blocking=blocking,
                critic_model=critic_model,
                boss_model=boss_model,
            )

    async def _run_iterations(
        self,
        *,
        ctx: AcbRunContext,
        max_iter: int,
        allow_syn: bool,
        blocking: frozenset[str],
        critic_model: str | None,
        boss_model: str | None,
    ) -> AcbOrchestrationOutcome:
        observability = get_observability()
        iterations: list[AcbIterationRecord] = []
        total_usage: UsageInfo | None = None
        revision_instructions: str | None = None
        last_candidate_bundle: StructuredEstimateBundle | None = None
        last_candidate: EstimationResult | None = None
        final_path: AcbFinalPath = "accept"
        final_bundle: StructuredEstimateBundle | None = None
        final_result: EstimationResult | None = None

        for iteration in range(1, max_iter + 1):
            with observability.start_span("acb_actor", attributes={"iteration": iteration}):
                actor_started = perf_counter()
                actor_bundle = await self._run_actor(
                    ctx,
                    revision_instructions=revision_instructions,
                    iteration=iteration,
                )
                actor_ms = int((perf_counter() - actor_started) * 1000)
            last_candidate_bundle = actor_bundle
            last_candidate = actor_bundle.result
            total_usage = _merge_usage(total_usage, actor_bundle.usage)

            logger.info(
                "acb_actor_completed",
                extra={
                    "iteration": iteration,
                    "latency_ms": actor_ms,
                    "usage": _usage_summary(actor_bundle.usage),
                },
            )

            with observability.start_span("acb_critic", attributes={"iteration": iteration}):
                critic_started = perf_counter()
                critic_feedback, critic_usage, critic_model_used = await self._run_critic(
                    ctx,
                    candidate=actor_bundle.result,
                    critic_model=critic_model,
                )
                critic_ms = int((perf_counter() - critic_started) * 1000)
            total_usage = _merge_usage(total_usage, critic_usage)

            logger.info(
                "acb_critic_completed",
                extra={
                    "iteration": iteration,
                    "issue_count": len(critic_feedback.issues),
                    "by_severity": count_issues_by_severity(critic_feedback.issues),
                    "by_category": count_issues_by_category(critic_feedback.issues),
                    "latency_ms": critic_ms,
                },
            )

            with observability.start_span("acb_boss", attributes={"iteration": iteration}):
                boss_started = perf_counter()
                boss_decision, boss_usage, boss_model_used = await self._run_boss(
                    ctx,
                    candidate=actor_bundle.result,
                    critic_feedback=critic_feedback,
                    iteration=iteration,
                    max_iterations=max_iter,
                    boss_model=boss_model,
                )
                boss_ms = int((perf_counter() - boss_started) * 1000)
            total_usage = _merge_usage(total_usage, boss_usage)

            normalized = normalize_boss_decision(
                boss_decision,
                iteration=iteration,
                max_iterations=max_iter,
                feedback=critic_feedback,
                blocking_severities=blocking,
                allow_synthesize=allow_syn,
            )

            logger.info(
                "acb_boss_decided",
                extra={
                    "action": normalized.action.value,
                    "iteration": iteration,
                    "budget_remaining": actor_budget_remaining(iteration, max_iterations=max_iter),
                },
            )

            iteration_usage = _merge_usage(
                _merge_usage(actor_bundle.usage, critic_usage),
                boss_usage,
            )
            iterations.append(
                AcbIterationRecord(
                    iteration=iteration,
                    boss_action=normalized.action,
                    critic_issue_counts=count_issues_by_severity(critic_feedback.issues),
                    actor_model=actor_bundle.model,
                    critic_model=critic_model_used,
                    boss_model=boss_model_used,
                    timings_ms={"actor": actor_ms, "critic": critic_ms, "boss": boss_ms},
                    usage=iteration_usage,
                )
            )

            if normalized.action == BossAction.accept:
                final_path = "accept"
                final_bundle = actor_bundle
                final_result = actor_bundle.result
                break

            if normalized.action == BossAction.synthesize:
                with observability.start_span("acb_synthesize", attributes={"iteration": iteration}):
                    synth_started = perf_counter()
                    synth_result, synth_bundle = await self._run_synthesize(
                        ctx,
                        candidate=actor_bundle.result,
                        critic_feedback=critic_feedback,
                        boss_model=boss_model,
                    )
                    synth_ms = int((perf_counter() - synth_started) * 1000)
                total_usage = _merge_usage(total_usage, synth_bundle.usage)
                final_path = "synthesize" if iteration < max_iter else "revise_exhausted_synthesize"
                final_bundle = synth_bundle
                final_result = synth_result
                logger.info(
                    "acb_synthesize_completed",
                    extra={"iteration": iteration, "latency_ms": synth_ms},
                )
                break

            revision_instructions = normalized.revision_instructions
            if not should_continue_loop(normalized, iteration=iteration, max_iterations=max_iter):
                final_path = "accept_on_budget_exhausted"
                final_bundle = actor_bundle
                final_result = actor_bundle.result
                break

        if final_bundle is None or final_result is None:
            assert last_candidate_bundle is not None and last_candidate is not None
            final_bundle = last_candidate_bundle
            final_result = last_candidate
            final_path = "accept_fallback"

        trace = AcbTrace(
            enabled=True,
            iterations=iterations,
            final_path=final_path,
            total_usage=total_usage,
            prompt_version_acb=ACB_PROMPT_VERSION,
        )

        logger.info(
            "acb_orchestration_finished",
            extra={
                "final_path": final_path,
                "iterations": len(iterations),
                "total_tokens": total_usage.total_tokens if total_usage else 0,
            },
        )

        return AcbOrchestrationOutcome(
            bundle=final_bundle,
            trace=trace,
            final_path=final_path,
            final_result=final_result,
        )

    async def _run_actor(
        self,
        ctx: AcbRunContext,
        *,
        revision_instructions: str | None,
        iteration: int,
    ) -> StructuredEstimateBundle:
        actor_prompts = render_acb_actor_prompts(
            assessment_surface=ctx.assessment_surface,
            project_metadata=ctx.project_metadata,
            revision_instructions=revision_instructions,
            iteration=iteration,
        )
        system_override = ctx.system_prompt_override or ""
        if actor_prompts.system_prompt.strip():
            system_override = f"{system_override}\n\n{actor_prompts.system_prompt}".strip()
        return await self._estimation.estimate_structured(
            ctx.request,
            assessment_surface=ctx.assessment_surface,
            skip_domain_guardrail=ctx.skip_domain_guardrail,
            system_prompt_override=system_override or None,
            user_prompt_override=ctx.user_prompt_override,
            messages_override=ctx.messages_override,
        )

    async def _run_critic(
        self,
        ctx: AcbRunContext,
        *,
        candidate: EstimationResult,
        critic_model: str | None,
    ) -> tuple[CriticFeedback, UsageInfo | None, str]:
        prompts = render_acb_critic_prompts(
            candidate=candidate,
            assessment_surface=ctx.assessment_surface,
            project_metadata=ctx.project_metadata,
        )
        try:
            feedback, usage, _finish = await self._structured_call(
                response_model=CriticFeedback,
                system_prompt=prompts.system_prompt,
                user_prompt=prompts.user_prompt,
                model_override=critic_model or self._settings.acb_critic_model,
            )
            return feedback, usage, _model_name(critic_model, self._settings.acb_critic_model)
        except (StructuredCompletionError, ValidationError) as exc:
            logger.warning(
                "acb_critic_parse_failed",
                extra={"error_type": type(exc).__name__},
            )
            fallback = CriticFeedback(
                schema_version="1",
                overall_assessment="pass",
                issues=[],
                summary="Critic parse failed; proceeding with empty issues.",
            )
            return fallback, None, _model_name(critic_model, self._settings.acb_critic_model)

    async def _run_boss(
        self,
        ctx: AcbRunContext,
        *,
        candidate: EstimationResult,
        critic_feedback: CriticFeedback,
        iteration: int,
        max_iterations: int,
        boss_model: str | None,
    ) -> tuple[BossDecision, UsageInfo | None, str]:
        budget_remaining = actor_budget_remaining(iteration, max_iterations=max_iterations)
        prompts = render_acb_boss_prompts(
            candidate=candidate,
            critic_feedback=critic_feedback,
            iteration=iteration,
            max_iterations=max_iterations,
            budget_remaining=budget_remaining,
        )
        try:
            decision, usage, _finish = await self._structured_call(
                response_model=BossDecision,
                system_prompt=prompts.system_prompt,
                user_prompt=prompts.user_prompt,
                model_override=boss_model or self._settings.acb_boss_model,
            )
            return decision, usage, _model_name(boss_model, self._settings.acb_boss_model)
        except (StructuredCompletionError, ValidationError) as exc:
            logger.error(
                "acb_boss_parse_failed",
                extra={"error_type": type(exc).__name__},
            )
            fallback = BossDecision(
                action=BossAction.accept,
                reasoning="Boss parse failed; accepting Actor candidate.",
                revision_instructions=None,
                confidence_in_decision=0.0,
            )
            return fallback, None, _model_name(boss_model, self._settings.acb_boss_model)

    async def _run_synthesize(
        self,
        ctx: AcbRunContext,
        *,
        candidate: EstimationResult,
        critic_feedback: CriticFeedback,
        boss_model: str | None,
    ) -> tuple[EstimationResult, StructuredEstimateBundle]:
        prompts = render_acb_boss_prompts(
            candidate=candidate,
            critic_feedback=critic_feedback,
            iteration=1,
            max_iterations=1,
            budget_remaining=0,
        )
        system_prompt = (
            f"{prompts.system_prompt}\n\n"
            "You must now produce the final integrated EstimationResult JSON. "
            "Incorporate valid Critic fixes while preserving coherent scope."
        )
        try:
            result, usage, finish = await self._structured_call(
                response_model=EstimationResult,
                system_prompt=system_prompt,
                user_prompt=prompts.user_prompt,
                model_override=boss_model or self._settings.acb_boss_model,
            )
        except (StructuredCompletionError, ValidationError):
            actor_bundle = await self._run_actor(ctx, revision_instructions=None, iteration=1)
            return actor_bundle.result, actor_bundle

        provider = self._estimation._first_litellm_route()
        bundle = StructuredEstimateBundle(
            result=result,
            prompt_version=ACB_PROMPT_VERSION,
            examples_version="acb/synthesize",
            model=provider.model if provider else "unknown",
            provider=provider.name if provider else "unknown",
            usage=usage,
            degraded=False,
            finish_reason=finish,
        )
        return result, bundle

    async def _structured_call(
        self,
        *,
        response_model: type[TModel],
        system_prompt: str,
        user_prompt: str,
        model_override: str,
    ) -> tuple[TModel, UsageInfo | None, str | None]:
        provider = self._estimation._first_litellm_route()
        if provider is None:
            raise StructuredCompletionError("No LiteLLM provider configured for ACB role call.")
        litellm_model, api_key, timeout = provider.litellm_route()
        if model_override.strip():
            litellm_model = model_override.strip()
        return await self._structured_complete(
            litellm_model=litellm_model,
            chain_provider=provider.name,
            api_key=api_key,
            timeout_seconds=timeout,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_output_tokens=self._settings.estimation_output_tokens_max,
            response_model=response_model,
            max_attempts=self._settings.structured_output_max_attempts,
            messages=None,
        )


def _merge_usage(left: UsageInfo | None, right: UsageInfo | None) -> UsageInfo | None:
    if left is None:
        return right
    if right is None:
        return left
    return UsageInfo(
        prompt_tokens=left.prompt_tokens + right.prompt_tokens,
        completion_tokens=left.completion_tokens + right.completion_tokens,
        total_tokens=left.total_tokens + right.total_tokens,
        preprocessing_input_tokens=left.preprocessing_input_tokens + right.preprocessing_input_tokens,
        preprocessing_output_tokens=left.preprocessing_output_tokens + right.preprocessing_output_tokens,
    )


def _usage_summary(usage: UsageInfo | None) -> dict[str, int] | None:
    if usage is None:
        return None
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }


def _model_name(override: str | None, settings_value: str) -> str:
    if override and override.strip():
        return override.strip()
    if settings_value.strip():
        return settings_value.strip()
    return "default"
