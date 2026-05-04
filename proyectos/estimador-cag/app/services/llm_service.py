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
PROMPT_VERSION = "v6"
EXAMPLES_VERSION = "file-mode-v4-estimator-layout"

_EXTRACTION_MAX_TOKENS = 1500

INLINE_CLEANING_BLOCK = """\
The transcription you receive is from a real meeting and may contain:
- Informal small talk you must ignore
- Implicit requirements you must surface explicitly
- Contradictions where you must trust the most recent statement
- Non-technical jargon you must interpret

Extract ONLY the functional and technical requirements relevant to the estimation."""

EXTRACTION_SYSTEM_PROMPT = (
    "You are an analyst. Read the meeting transcription and produce a clean, "
    "deduplicated bullet list of functional requirements, non-functional "
    "requirements, integrations, constraints and explicit deadlines. Ignore "
    "fillers, divagations and off-topic remarks. Output Markdown only."
)


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
    finish_reason: str | None = None


def build_system_prompt(
    examples: list[EstimationExample],
    mode: EstimationMode,
    *,
    inline_cleaning: bool = False,
) -> str:
    """Compose the system message: full mode-specific instructions plus static few-shot examples."""

    system_preamble = load_mode_prompt(mode).strip()
    cleaning = INLINE_CLEANING_BLOCK if inline_cleaning else ""
    parts: list[str] = [system_preamble]
    if cleaning:
        parts.append("\n\n" + cleaning)
    parts.append("\n\n## Reference estimation examples\n")
    for index, example in enumerate(examples, start=1):
        parts.append(f"\n### Example {index} — meeting summary\n{example.meeting_summary}\n")
        parts.append(f"\n### Example {index} — estimate\n{example.estimation}\n")
    return "".join(parts)


def _merge_preprocessing_usage(
    main: UsageInfo | None,
    extra_prep_in: int,
    extra_prep_out: int,
) -> UsageInfo | None:
    """Add phase-1 preprocessing token counts onto the main completion usage."""

    if extra_prep_in == 0 and extra_prep_out == 0:
        return main
    if main is None:
        return UsageInfo(
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            preprocessing_input_tokens=extra_prep_in,
            preprocessing_output_tokens=extra_prep_out,
        )
    return UsageInfo(
        prompt_tokens=main.prompt_tokens,
        completion_tokens=main.completion_tokens,
        total_tokens=main.total_tokens,
        preprocessing_input_tokens=extra_prep_in + main.preprocessing_input_tokens,
        preprocessing_output_tokens=extra_prep_out + main.preprocessing_output_tokens,
    )


class EstimationService:
    """Coordinates prompt construction and provider-chain completion calls."""

    def __init__(self, settings: Settings, providers: list[LLMProvider]) -> None:
        self._settings = settings
        self._providers = providers

    async def _extract_requirements_two_phase(self, transcription: str) -> tuple[str, int, int]:
        """Cheap phase-1 call: raw transcription to structured requirements (Markdown)."""

        cap = min(
            _EXTRACTION_MAX_TOKENS,
            self._settings.estimation_standard_output_tokens_max,
        )
        for provider in self._providers:
            if provider.name == "static_fallback":
                continue
            try:
                res = await provider.complete(
                    system_prompt=EXTRACTION_SYSTEM_PROMPT,
                    user_prompt=transcription,
                    max_output_tokens=cap,
                )
            except ProviderError:
                continue
            text = res.text.strip()
            if not text:
                continue
            prep_in = prep_out = 0
            if res.usage is not None:
                prep_in = res.usage.prompt_tokens
                prep_out = res.usage.completion_tokens
            logger.info(
                "preprocessing_two_phase_extracted",
                extra={"provider": provider.name, "prep_in": prep_in, "prep_out": prep_out},
            )
            return text, prep_in, prep_out
        raise EstimationError(
            "Two-phase preprocessing requires at least one live LLM provider before static fallback."
        )

    async def estimate(self, transcription: str, *, preprocessing: str = "none") -> EstimationResult:
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
        if self._settings.forced_estimation_mode is not None:
            mode = self._settings.forced_estimation_mode
            logger.info(
                "estimation_mode_forced",
                extra={
                    "mode": mode.value,
                    "recommended_mode": recommended_mode.value,
                },
            )

        if preprocessing not in {"none", "inline_cleaning", "two_phase"}:
            raise EstimationError("Invalid preprocessing mode.")

        user_text = text
        phase1_prep_in = 0
        phase1_prep_out = 0
        if preprocessing == "two_phase":
            user_text, phase1_prep_in, phase1_prep_out = await self._extract_requirements_two_phase(text)

        system_prompt = build_system_prompt(
            load_examples(mode),
            mode,
            inline_cleaning=(preprocessing == "inline_cleaning"),
        )
        max_output_tokens = self._settings.completion_token_cap_for_mode(mode)
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
                    "max_output_tokens": max_output_tokens,
                    "estimation_mode": mode.value,
                },
            )
            try:
                result = await provider.complete(
                    system_prompt=system_prompt,
                    user_prompt=user_text,
                    max_output_tokens=max_output_tokens,
                )
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

            merged_usage = _merge_preprocessing_usage(result.usage, phase1_prep_in, phase1_prep_out)

            return EstimationResult(
                estimation=result.text,
                provider=result.provider,
                model=result.model,
                usage=merged_usage,
                mode=mode,
                assessment=assessment_summary,
                mode_eligibility=mode_eligibility,
                degraded=degraded,
                finish_reason=result.finish_reason,
            )

        logger.warning("chain_exhausted", extra={"providers_tried": provider_names})
        if isinstance(last_error, ProviderConfigError):
            raise EstimationError(str(last_error)) from last_error
        raise EstimationError("All providers failed.")
