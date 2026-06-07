"""Unit tests for ActorCriticBossOrchestrator with mocked LLM roles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeVar
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.config import Settings
from app.guardrails.acb.context import AcbRunContext
from app.guardrails.acb.orchestrator import ActorCriticBossOrchestrator
from app.schemas.acb.boss import BossAction, BossDecision
from app.schemas.acb.critic import CriticFeedback, CriticIssue, CriticIssueCategory, CriticIssueSeverity
from app.schemas.estimation_request import (
    DetailLevel,
    EstimationRequest,
    Industry,
    OutputFormat,
    ProjectType,
    TargetAudience,
)
from app.schemas.estimation_result import (
    EstimationLineItem,
    EstimationPhase,
    EstimationResult,
    EstimationTotals,
)
from app.services.llm_service import EstimationService, StructuredEstimateBundle
from app.services.llm_types import UsageInfo

TModel = TypeVar("TModel", bound=BaseModel)


def _request() -> EstimationRequest:
    return EstimationRequest(
        project_name="ACB test project",
        project_summary="Twenty chars minimum!!",
        project_type=ProjectType.web_saas,
        target_audience=TargetAudience.b2b_smb,
        industry=Industry.fintech,
        project_description="Build a web application with authentication and reporting dashboard." + ("x" * 40),
        detail_level=DetailLevel.medium,
        output_format=OutputFormat.phases_table,
    )


def _candidate(title: str = "ACB candidate") -> EstimationResult:
    li = EstimationLineItem(name="Feature work", hours=20.0, cost_eur=1000.0)
    return EstimationResult(
        title=title,
        summary="A" * 30,
        phases=[EstimationPhase(name="Delivery", items=[li])],
        line_items=[],
        totals=EstimationTotals(hours=20.0, cost_eur=1000.0),
        duration_weeks=2.0,
        confidence=0.6,
    )


def _actor_bundle(title: str = "ACB candidate") -> StructuredEstimateBundle:
    return StructuredEstimateBundle(
        result=_candidate(title),
        prompt_version="estimation/v2",
        examples_version="test",
        model="gpt-test",
        provider="openai",
        usage=UsageInfo(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        degraded=False,
        finish_reason="stop",
    )


@dataclass
class ScriptedStructuredLLM:
    critic_feedback: CriticFeedback
    boss_sequence: list[BossDecision] = field(default_factory=list)
    synthesize_result: EstimationResult | None = None
    calls: list[type[BaseModel]] = field(default_factory=list)

    async def complete_structured(
        self,
        *,
        litellm_model: str,
        chain_provider: str,
        api_key: str,
        timeout_seconds: float,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        response_model: type[TModel],
        max_attempts: int,
        messages: list[dict[str, str]] | None = None,
    ) -> tuple[TModel, UsageInfo | None, str | None]:
        del litellm_model, chain_provider, api_key, timeout_seconds, system_prompt
        del user_prompt, max_output_tokens, max_attempts, messages
        self.calls.append(response_model)
        usage = UsageInfo(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        if response_model is CriticFeedback:
            return self.critic_feedback, usage, "stop"  # type: ignore[return-value]
        if response_model is BossDecision:
            if not self.boss_sequence:
                raise AssertionError("BossDecision requested but boss_sequence is empty")
            decision = self.boss_sequence.pop(0)
            return decision, usage, "stop"  # type: ignore[return-value]
        if response_model is EstimationResult:
            result = self.synthesize_result or _candidate("Synthesized final")
            return result, usage, "stop"  # type: ignore[return-value]
        raise TypeError(f"Unsupported response_model: {response_model!r}")


@dataclass(frozen=True)
class _FakeLitellmRoute:
    name: str = "openai"
    model: str = "gpt-test"

    def litellm_route(self) -> tuple[str, str, float]:
        return ("openai/gpt-test", "sk-test", 30.0)


def _mock_estimation_service() -> AsyncMock:
    estimation = AsyncMock(spec=EstimationService)
    estimation._first_litellm_route = lambda: _FakeLitellmRoute()
    return estimation


def _orchestrator(
    estimation_service: EstimationService,
    settings: Settings,
    scripted: ScriptedStructuredLLM,
) -> ActorCriticBossOrchestrator:
    return ActorCriticBossOrchestrator(
        estimation_service,
        settings,
        structured_complete=scripted.complete_structured,
    )


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ACB_ENABLED", "false")
    monkeypatch.setenv("ACB_MAX_ITERATIONS", "2")
    from app.config import get_settings

    get_settings.cache_clear()
    return Settings(_env_file=None)


@pytest.mark.asyncio
async def test_acb_accept_on_first_iteration(settings: Settings) -> None:
    estimation = _mock_estimation_service()
    estimation.estimate_structured = AsyncMock(return_value=_actor_bundle())

    scripted = ScriptedStructuredLLM(
        critic_feedback=CriticFeedback(
            schema_version="1",
            overall_assessment="pass",
            issues=[],
            summary="Looks good.",
        ),
        boss_sequence=[
            BossDecision(
                action=BossAction.accept,
                reasoning="No material issues.",
                revision_instructions=None,
                confidence_in_decision=0.9,
            )
        ],
    )
    orchestrator = _orchestrator(estimation, settings, scripted)
    ctx = AcbRunContext(request=_request(), assessment_surface="Build auth and reporting.")

    outcome = await orchestrator.run(ctx)

    assert outcome.final_path == "accept"
    assert outcome.trace.iterations[0].boss_action == BossAction.accept
    assert estimation.estimate_structured.await_count == 1
    assert scripted.calls == [CriticFeedback, BossDecision]


@pytest.mark.asyncio
async def test_acb_revise_then_accept(settings: Settings) -> None:
    estimation = _mock_estimation_service()
    estimation.estimate_structured = AsyncMock(
        side_effect=[_actor_bundle("Draft"), _actor_bundle("Revised")]
    )

    major_issue = CriticIssue(
        category=CriticIssueCategory.scope_mismatch,
        severity=CriticIssueSeverity.major,
        message="Missing reporting scope.",
        affected_area="scope",
        suggested_fix="Add reporting module.",
        evidence=None,
    )
    scripted = ScriptedStructuredLLM(
        critic_feedback=CriticFeedback(
            schema_version="1",
            overall_assessment="fail",
            issues=[major_issue],
            summary="Scope gap.",
        ),
        boss_sequence=[
            BossDecision(
                action=BossAction.revise,
                reasoning="Fixable in one pass.",
                revision_instructions="- Add reporting scope",
                confidence_in_decision=0.8,
            ),
            BossDecision(
                action=BossAction.accept,
                reasoning="Revision addressed issues.",
                revision_instructions=None,
                confidence_in_decision=0.85,
            ),
        ],
    )
    orchestrator = _orchestrator(estimation, settings, scripted)
    ctx = AcbRunContext(request=_request(), assessment_surface="Auth and reporting.")

    outcome = await orchestrator.run(ctx)

    assert outcome.final_path == "accept"
    assert estimation.estimate_structured.await_count == 2
    assert len(outcome.trace.iterations) == 2


@pytest.mark.asyncio
async def test_acb_budget_exhausted_triggers_synthesize(settings: Settings) -> None:
    estimation = _mock_estimation_service()
    estimation.estimate_structured = AsyncMock(return_value=_actor_bundle())

    major_issue = CriticIssue(
        category=CriticIssueCategory.arithmetic_inconsistency,
        severity=CriticIssueSeverity.critical,
        message="Totals mismatch.",
        affected_area="totals",
        suggested_fix="Fix totals.",
        evidence=None,
    )
    scripted = ScriptedStructuredLLM(
        critic_feedback=CriticFeedback(
            schema_version="1",
            overall_assessment="fail",
            issues=[major_issue],
            summary="Critical totals issue.",
        ),
        boss_sequence=[
            BossDecision(
                action=BossAction.revise,
                reasoning="Try revision.",
                revision_instructions="- Fix totals",
                confidence_in_decision=0.7,
            ),
            BossDecision(
                action=BossAction.revise,
                reasoning="Still broken.",
                revision_instructions="- Fix totals again",
                confidence_in_decision=0.6,
            ),
        ],
        synthesize_result=_candidate("Final synthesized"),
    )
    orchestrator = _orchestrator(estimation, settings, scripted)
    ctx = AcbRunContext(request=_request(), assessment_surface="Totals check.")

    outcome = await orchestrator.run(ctx, max_iterations=2, allow_synthesize=True)

    assert outcome.final_path == "revise_exhausted_synthesize"
    assert outcome.final_result.title == "Final synthesized"
    assert EstimationResult in scripted.calls
