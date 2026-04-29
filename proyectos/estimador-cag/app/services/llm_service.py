"""CAG-style estimation service orchestrating a provider chain."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter

from app.config import Settings
from app.context.examples import EstimationExample, load_examples
from app.context.prompt_loader import load_mode_prompt
from app.services.estimation_engine import (
    EstimationMode,
    assess_and_select_mode,
    evaluate_mode_eligibility,
    enforce_mode_eligibility,
    InputAssessment,
    ModeEligibility,
    summarize_assessment,
    validate_mode_output,
)
from app.services.domain_guardrails import check_estimation_domain
from app.services.providers.base import (
    LLMProvider,
    ProviderConfigError,
    ProviderError,
    ProviderInvalidResponseError,
    UsageInfo,
)

logger = logging.getLogger(__name__)
PROMPT_VERSION = "v4"
EXAMPLES_VERSION = "static-v1"


class EstimationError(Exception):
    """Raised when an estimate cannot be produced; message is safe for clients."""


class DomainGuardrailError(Exception):
    """Raised when input falls outside the estimation domain."""

    code = "out_of_domain"


@dataclass(frozen=True)
class EstimationResult:
    """Estimation text plus provider metadata used by the API layer."""

    estimation: str
    provider: str
    model: str
    usage: UsageInfo | None
    mode: EstimationMode = EstimationMode.STANDARD
    assessment: InputAssessment | None = None
    mode_eligibility: ModeEligibility | None = None
    degraded: bool = False


def build_system_prompt(examples: list[EstimationExample], mode: EstimationMode) -> str:
    """Compose the system message: full mode-specific instructions plus static few-shot examples."""

    system_preamble = load_mode_prompt(mode).strip()
    parts: list[str] = [system_preamble, "\n\n## Reference estimation examples\n"]
    for index, example in enumerate(examples, start=1):
        parts.append(f"\n### Example {index} — meeting summary\n{example.meeting_summary}\n")
        parts.append(f"\n### Example {index} — estimate\n{example.estimation}\n")
    return "".join(parts)


class EstimationService:
    """Coordinates prompt construction and provider-chain completion calls."""

    def __init__(self, settings: Settings, providers: list[LLMProvider]) -> None:
        self._settings = settings
        self._providers = providers

    async def estimate(self, transcription: str) -> EstimationResult:
        """Return generated estimation plus provider usage metadata."""

        text = transcription.strip()
        if not text:
            raise EstimationError("Transcription must not be empty.")

        if self._settings.llm_domain_guardrail_enabled:
            domain_decision = check_estimation_domain(text)
            if not domain_decision.accepted:
                logger.info("guardrail_rejected", extra={"reason": domain_decision.reason})
                raise DomainGuardrailError("Only software/project estimation requests are supported.")

        raw_assessment, recommended_mode = assess_and_select_mode(text)
        assessment_summary = summarize_assessment(raw_assessment, recommended_mode)
        mode_eligibility = evaluate_mode_eligibility(assessment_summary)
        mode = enforce_mode_eligibility(recommended_mode, mode_eligibility)
        system_prompt = build_system_prompt(load_examples(), mode)
        provider_names = [provider.name for provider in self._providers]
        last_error: ProviderError | None = None

        for attempt_index, provider in enumerate(self._providers, start=1):
            started = perf_counter()
            logger.info(
                "provider_attempted",
                extra={
                    "provider": provider.name,
                    "model": provider.model,
                    "attempt_index": attempt_index,
                },
            )
            try:
                result = await provider.complete(system_prompt=system_prompt, user_prompt=text)
            except ProviderConfigError as exc:
                logger.warning(
                    "provider_failed",
                    extra={
                        "provider": provider.name,
                        "model": provider.model,
                        "error_type": type(exc).__name__,
                        "attempt_index": attempt_index,
                    },
                )
                last_error = exc
                if self._settings.llm_auth_fallback:
                    continue
                raise EstimationError(str(exc)) from exc
            except ProviderError as exc:
                logger.warning(
                    "provider_failed",
                    extra={
                        "provider": provider.name,
                        "model": provider.model,
                        "error_type": type(exc).__name__,
                        "attempt_index": attempt_index,
                    },
                )
                last_error = exc
                continue
            except Exception as exc:
                logger.exception(
                    "provider_failed",
                    extra={
                        "provider": provider.name,
                        "model": provider.model,
                        "error_type": type(exc).__name__,
                        "attempt_index": attempt_index,
                    },
                )
                raise EstimationError("Unexpected provider failure.") from exc

            if result.provider != "static_fallback" and not validate_mode_output(result.text, mode):
                logger.warning(
                    "provider_invalid_structure",
                    extra={
                        "provider": result.provider,
                        "model": result.model,
                        "mode": mode.value,
                        "attempt_index": attempt_index,
                    },
                )
                last_error = ProviderInvalidResponseError(
                    f"Invalid markdown structure for mode '{mode.value}'."
                )
                continue

            logger.info(
                "provider_succeeded",
                extra={
                    "provider": result.provider,
                    "model": result.model,
                    "latency_ms": int((perf_counter() - started) * 1000),
                },
            )
            degraded = result.provider == "static_fallback"
            if degraded:
                logger.warning(
                    "chain_degraded",
                    extra={"static_fallback_used": True},
                )

            return EstimationResult(
                estimation=result.text,
                provider=result.provider,
                model=result.model,
                usage=result.usage,
                mode=mode,
                assessment=assessment_summary,
                mode_eligibility=mode_eligibility,
                degraded=degraded,
            )

        logger.warning("chain_exhausted", extra={"providers_tried": provider_names})
        if isinstance(last_error, ProviderConfigError):
            raise EstimationError(str(last_error)) from last_error
        raise EstimationError("All providers failed.")
