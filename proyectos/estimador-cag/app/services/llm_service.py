"""CAG-style estimation service orchestrating a provider chain."""

from __future__ import annotations

import logging
import json
from dataclasses import dataclass
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Any

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
from app.services.llm_types import (
    LLMProvider,
    ProviderConfigError,
    ProviderError,
    ProviderInvalidResponseError,
    StreamingLLMProvider,
    UsageInfo,
)

logger = logging.getLogger(__name__)
PROMPT_VERSION = "v7-guided-input"
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


@dataclass(frozen=True)
class _PreparedCall:
    """Inputs assembled for a single provider invocation (streaming or not)."""

    system_prompt: str
    user_text: str
    mode: EstimationMode
    max_output_tokens: int
    assessment: InputAssessment
    mode_eligibility: ModeEligibility
    phase1_prep_in: int
    phase1_prep_out: int


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


def _usage_dict_for_dev_sse(model: str, usage: UsageInfo | None) -> dict[str, Any] | None:
    """Serialize token usage for the SSE ``done`` event (same fields as REST when DEV_MODE is on)."""

    if usage is None:
        return None
    from app.schemas.estimations import UsageView
    from app.services.estimate_response_builder import estimate_cost_usd

    view = UsageView(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        preprocessing_input_tokens=usage.preprocessing_input_tokens,
        preprocessing_output_tokens=usage.preprocessing_output_tokens,
    )
    cost = estimate_cost_usd(model, view)
    payload: dict[str, Any] = view.model_dump()
    payload["estimated_cost_usd"] = cost
    return payload


class EstimationService:
    """Coordinates prompt construction and provider-chain completion calls."""

    def __init__(self, settings: Settings, providers: list[LLMProvider]) -> None:
        self._settings = settings
        self._providers = providers

    @staticmethod
    def serialize_sse_event(event: str, data: dict[str, Any]) -> str:
        """Build a single Server-Sent Event payload line block."""

        payload = json.dumps(data, separators=(",", ":"))
        return f"event: {event}\ndata: {payload}\n\n"

    async def stream_estimation(
        self,
        transcription: str,
        *,
        preprocessing: str = "none",
        assessment_input: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield SSE events for chunk, done, and error using native upstream streaming.

        Streaming-capable providers (those exposing `stream_complete`) emit one SSE
        `chunk` event per upstream delta. Providers without streaming support (e.g.
        the static fallback) are invoked through `complete()` and their full output
        is emitted as a single `chunk` event before `done`.

        The `done` event always includes ``{"status": "completed"}``. When
        ``DEV_MODE`` is enabled on settings, it may also include ``model``,
        ``provider``, and ``usage`` (token counts plus optional ``estimated_cost_usd``)
        aligned with ``POST /api/v1/estimate`` when the provider reports usage.
        """

        try:
            prepared = await self._prepare_call(
                transcription,
                preprocessing=preprocessing,
                assessment_input=assessment_input,
            )
        except DomainGuardrailError as exc:
            yield self.serialize_sse_event(
                "error",
                {"message": str(exc).strip() or "Out of domain."},
            )
            return
        except EstimationError as exc:
            yield self.serialize_sse_event(
                "error",
                {"message": str(exc).strip() or "Unable to stream estimation."},
            )
            return
        except Exception as exc:  # noqa: BLE001 — boundary: keep stream safe on unexpected prepare failure
            logger.exception("stream_prepare_failed")
            yield self.serialize_sse_event(
                "error",
                {"message": str(exc).strip() or "Unable to stream estimation."},
            )
            return

        last_error: ProviderError | None = None
        provider_names = [provider.name for provider in self._providers]

        for attempt_index, provider in enumerate(self._providers, start=1):
            started = perf_counter()
            logger.info(
                "provider_attempted_stream",
                extra={
                    "provider": provider.name,
                    "model": provider.model,
                    "attempt_index": attempt_index,
                    "max_output_tokens": prepared.max_output_tokens,
                    "estimation_mode": prepared.mode.value,
                    "supports_streaming": isinstance(provider, StreamingLLMProvider),
                },
            )

            try:
                emitted = False
                stream_main_usage: UsageInfo | None = None
                if isinstance(provider, StreamingLLMProvider):
                    async for part in provider.stream_complete(
                        prepared.system_prompt,
                        prepared.user_text,
                        max_output_tokens=prepared.max_output_tokens,
                    ):
                        if isinstance(part, UsageInfo):
                            stream_main_usage = part
                        elif part:
                            emitted = True
                            yield self.serialize_sse_event("chunk", {"content": part})
                else:
                    result = await provider.complete(
                        prepared.system_prompt,
                        prepared.user_text,
                        max_output_tokens=prepared.max_output_tokens,
                    )
                    stream_main_usage = result.usage
                    if result.text:
                        emitted = True
                        yield self.serialize_sse_event("chunk", {"content": result.text})
            except ProviderConfigError as exc:
                logger.warning(
                    "provider_failed_stream",
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
                yield self.serialize_sse_event(
                    "error",
                    {"message": str(exc).strip() or "Provider configuration error."},
                )
                return
            except ProviderError as exc:
                logger.warning(
                    "provider_failed_stream",
                    extra={
                        "provider": provider.name,
                        "model": provider.model,
                        "error_type": type(exc).__name__,
                        "attempt_index": attempt_index,
                    },
                )
                last_error = exc
                continue
            except Exception as exc:  # noqa: BLE001 — boundary: stop chain on unexpected failure
                logger.exception(
                    "provider_failed_stream",
                    extra={
                        "provider": provider.name,
                        "model": provider.model,
                        "error_type": type(exc).__name__,
                        "attempt_index": attempt_index,
                    },
                )
                yield self.serialize_sse_event(
                    "error",
                    {"message": "Unexpected provider failure."},
                )
                return

            if not emitted:
                last_error = ProviderInvalidResponseError(
                    f"{provider.name} returned an empty stream."
                )
                logger.warning(
                    "provider_failed_stream",
                    extra={
                        "provider": provider.name,
                        "model": provider.model,
                        "error_type": "empty_stream",
                        "attempt_index": attempt_index,
                    },
                )
                continue

            logger.info(
                "provider_succeeded_stream",
                extra={
                    "provider": provider.name,
                    "model": provider.model,
                    "latency_ms": int((perf_counter() - started) * 1000),
                },
            )
            merged_usage = _merge_preprocessing_usage(
                stream_main_usage,
                prepared.phase1_prep_in,
                prepared.phase1_prep_out,
            )
            done_payload: dict[str, Any] = {"status": "completed"}
            if self._settings.dev_mode:
                done_payload["model"] = provider.model
                done_payload["provider"] = provider.name
                usage_blob = _usage_dict_for_dev_sse(provider.model, merged_usage)
                if usage_blob is not None:
                    done_payload["usage"] = usage_blob
            yield self.serialize_sse_event("done", done_payload)
            return

        logger.warning("chain_exhausted_stream", extra={"providers_tried": provider_names})
        message = "All providers failed."
        if isinstance(last_error, ProviderConfigError) and str(last_error).strip():
            message = str(last_error).strip()
        yield self.serialize_sse_event("error", {"message": message})

    async def _prepare_call(
        self,
        transcription: str,
        *,
        preprocessing: str = "none",
        assessment_input: str | None = None,
    ) -> _PreparedCall:
        """Run the shared prelude (guardrail, mode, preprocessing) for both estimate paths.

        Raises `EstimationError` for invalid input or `DomainGuardrailError` for
        out-of-domain transcriptions.

        ``transcription`` is the full user message sent to the model (after preprocessing).
        When ``assessment_input`` is set, domain guardrail and adaptive mode selection run
        on that narrower surface instead of the full templated message.
        """

        text = transcription.strip()
        if not text:
            raise EstimationError("Transcription must not be empty.")

        surface_raw = assessment_input.strip() if assessment_input else ""
        surface = surface_raw if surface_raw else text

        if self._settings.llm_domain_guardrail_enabled:
            domain_decision = check_estimation_domain(surface)
            if not domain_decision.accepted:
                logger.info("guardrail_rejected", extra={"reason": domain_decision.reason})
                raise DomainGuardrailError("Only software/project estimation requests are supported.")

        raw_assessment, recommended_mode = assess_and_select_mode(surface)
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
        return _PreparedCall(
            system_prompt=system_prompt,
            user_text=user_text,
            mode=mode,
            max_output_tokens=max_output_tokens,
            assessment=assessment_summary,
            mode_eligibility=mode_eligibility,
            phase1_prep_in=phase1_prep_in,
            phase1_prep_out=phase1_prep_out,
        )

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

    async def estimate(
        self,
        transcription: str,
        *,
        preprocessing: str = "none",
        assessment_input: str | None = None,
    ) -> EstimationResult:
        """Return generated estimation plus provider usage metadata."""

        prepared = await self._prepare_call(
            transcription,
            preprocessing=preprocessing,
            assessment_input=assessment_input,
        )
        system_prompt = prepared.system_prompt
        user_text = prepared.user_text
        mode = prepared.mode
        max_output_tokens = prepared.max_output_tokens
        assessment_summary = prepared.assessment
        mode_eligibility = prepared.mode_eligibility
        phase1_prep_in = prepared.phase1_prep_in
        phase1_prep_out = prepared.phase1_prep_out
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
