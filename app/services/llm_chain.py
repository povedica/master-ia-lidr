"""LLM chain: LiteLLM-backed rows, static fallback, and `build_provider_chain`."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable

from app.config import Settings
from app.services.ai_model_service import acomplete_chat, astream_chat
from app.services.estimation_engine import EstimationMode
from app.services.llm_types import (
    LLMProvider,
    ProviderConfigError,
    ProviderResult,
    UsageInfo,
)

logger = logging.getLogger(__name__)

ProviderFactory = Callable[[Settings], LLMProvider | None]


class LitellmChainProvider:
    """One configured LiteLLM route (e.g. OpenAI or Anthropic credentials)."""

    def __init__(
        self,
        *,
        name: str,
        litellm_model: str,
        api_key: str,
        timeout_seconds: float,
    ) -> None:
        self.name = name
        self.model = litellm_model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_output_tokens: int,
    ) -> ProviderResult:
        outcome = await acomplete_chat(
            litellm_model=self.model,
            system_message=system_prompt,
            user_message=user_prompt,
            max_output_tokens=max_output_tokens,
            timeout_seconds=self._timeout_seconds,
            chain_provider=self.name,
            api_key=self._api_key,
        )
        return ProviderResult(
            text=outcome.text,
            provider=self.name,
            model=outcome.model,
            usage=outcome.usage,
            finish_reason=outcome.finish_reason,
        )

    async def stream_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_output_tokens: int,
    ) -> AsyncIterator[str | UsageInfo]:
        """Yield text deltas from the upstream LiteLLM streaming completion."""

        async for delta in astream_chat(
            litellm_model=self.model,
            system_message=system_prompt,
            user_message=user_prompt,
            max_output_tokens=max_output_tokens,
            timeout_seconds=self._timeout_seconds,
            chain_provider=self.name,
            api_key=self._api_key,
        ):
            yield delta


_DEGRADED_PREAMBLE = (
    "## Estimation: Temporary degraded mode\n\n"
    "### Assumptions\n"
    "- Live model providers are currently unavailable.\n"
    "- This response is a coarse fallback and should be reviewed manually.\n\n"
)

_TASKS_TABLE = (
    "### Tasks\n"
    "| Task | Hours |\n"
    "|------|------:|\n"
    "| Requirements clarification | 4 |\n"
    "| Technical design draft | 6 |\n"
    "| Implementation + tests | 16 |\n"
    "| QA + deployment checklist | 6 |\n"
    "| **Total** | **32** |\n\n"
)

_DELIVERY_NOTES = (
    "### Delivery notes\n"
    "Re-run the estimate when model providers recover to replace this degraded output."
)

_STANDARD_BUDGET = (
    "## Effort Summary\n"
    "- Base effort: 28 hours\n"
    "- Buffer (~14%): 4 hours\n"
    "- **Total: 32 hours**\n\n"
    "## Budget (indicative)\n"
    "- EUR range (low–high): approximately **1,700–2,400 EUR** (aligned with ~32h and a blended "
    "~55–75 EUR/h placeholder assumption; illustrative only, not a quote)\n"
    "- Uses the same fictional rate-card band (35–100 EUR/h) as live mode when no custom rates are supplied\n\n"
)

_PROFESSIONAL_BUDGET = (
    "## Effort Estimation\n"
    "- Optimistic: 28 hours\n"
    "- Realistic: 32 hours\n"
    "- Conservative: 38 hours\n\n"
    "## Budget (indicative)\n"
    "| Bucket | Hours | EUR/h (illustrative) | Subtotal (EUR) |\n"
    "|--------|------:|---------------------:|---------------:|\n"
    "| Build + tests | 16 | 58 | 928 |\n"
    "| Design / clarification | 6 | 52 | 312 |\n"
    "| QA + release checklist | 6 | 45 | 270 |\n"
    "| PM / coordination buffer | 4 | 48 | 192 |\n"
    "| **Total (realistic path)** | **32** | blended ~56 | **~1,700** |\n\n"
    "- Scenario bands (placeholder math): optimistic **~1,450–1,750 EUR** | realistic **~1,650–2,050 EUR** | "
    "conservative **~2,000–2,600 EUR**\n"
    "- Not a commercial quote; replace with a live-model estimate when providers recover\n\n"
)

_EXPERT_BUDGET = (
    "## Effort Scenarios\n"
    "- Best case: 28 hours\n"
    "- Realistic: 32 hours\n"
    "- Worst case: 40 hours\n\n"
    "## Profile breakdown\n"
    "Illustrative staffing for the **realistic** path (32h total); rates from the placeholder card.\n\n"
    "| Role | Hours | EUR/h | Subtotal (EUR) |\n"
    "|------|------:|------:|---------------:|\n"
    "| Mid-level developer | 14 | 58 | 812 |\n"
    "| Senior developer | 4 | 78 | 312 |\n"
    "| QA engineer | 6 | 42 | 252 |\n"
    "| PM / delivery lead | 4 | 48 | 192 |\n"
    "| Tech lead / architect | 4 | 100 | 400 |\n"
    "| **Total** | **32** | — | **~1,968** |\n\n"
    "- Best/worst scenarios would shift senior/lead and QA share; this table is a single-path illustration only\n\n"
    "## Budget (indicative)\n"
    "- Best case EUR band: **~1,500–1,900** | Realistic: **~1,750–2,350** | Worst case: **~2,400–3,200**\n"
    "- Expanded placeholder breakdown (realistic path, 32h):\n"
    "| Phase / driver | Hours | EUR/h | Subtotal (EUR) |\n"
    "|----------------|------:|------:|----------------:|\n"
    "| Core implementation | 16 | 58 | 928 |\n"
    "| Integration / unknowns buffer | 6 | 72 | 432 |\n"
    "| QA + hardening | 6 | 45 | 270 |\n"
    "| Coordination + overhead | 4 | 48 | 192 |\n\n"
    "- MVP-only vs full scope: this fallback cannot split accurately; re-run with a live model.\n"
    "- Illustrative placeholder rates only; not a binding quote\n\n"
    "## Cost Drivers\n"
    "- Provider outage forces static template; largest uncertainty is integration depth not captured here\n\n"
)


def _infer_mode_from_system_prompt(system_prompt: str) -> EstimationMode:
    """Recover estimation mode from the composed system prompt (mode fragment is always first)."""

    head = system_prompt[:4000].lower()
    if "expert review" in head and "principal software architect" in head:
        return EstimationMode.EXPERT_REVIEW
    if "professional mode" in head:
        return EstimationMode.PROFESSIONAL
    if "operating in basic mode" in head:
        return EstimationMode.BASIC
    if "standard mode" in head:
        return EstimationMode.STANDARD
    if "basic mode" in head:
        return EstimationMode.BASIC
    return EstimationMode.STANDARD


def _build_degraded_markdown(mode: EstimationMode) -> str:
    parts: list[str] = [_DEGRADED_PREAMBLE]

    if mode is EstimationMode.BASIC:
        parts.append(
            "## MVP Scope\n"
            "Placeholder: small delivery slice only—replace with a live estimate.\n\n"
            "## Effort Estimate\n"
            "- Estimated range: 28–40 hours (placeholder band around the 32h template total)\n"
            "- Confidence: low\n\n"
            "## Risks\n"
            "- Fallback text is not validated against your transcription\n"
            "- Effort and scope are not inferred from the meeting content in degraded mode\n\n"
        )
    else:
        parts.append(_TASKS_TABLE)

    if mode is EstimationMode.STANDARD:
        parts.append(_STANDARD_BUDGET)
    elif mode is EstimationMode.PROFESSIONAL:
        parts.append(_PROFESSIONAL_BUDGET)
    elif mode is EstimationMode.EXPERT_REVIEW:
        parts.append(_EXPERT_BUDGET)

    parts.append(_DELIVERY_NOTES)
    return "".join(parts)


class StaticFallbackProvider:
    """Deterministic fallback provider used as last resort."""

    name = "static_fallback"
    model = "static-v1"

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_output_tokens: int,
    ) -> ProviderResult:
        del user_prompt
        del max_output_tokens
        mode = _infer_mode_from_system_prompt(system_prompt)
        text = _build_degraded_markdown(mode)
        return ProviderResult(
            text=text,
            provider=self.name,
            model=self.model,
            usage=None,
            finish_reason="stop",
        )


def _openai_factory(settings: Settings) -> LLMProvider | None:
    if not settings.openai_api_key:
        logger.info(
            "provider_skipped",
            extra={"provider": "openai", "reason": "missing_api_key"},
        )
        return None
    return LitellmChainProvider(
        name="openai",
        litellm_model=settings.openai_litellm_model_id(),
        api_key=settings.openai_api_key,
        timeout_seconds=settings.openai_timeout_seconds,
    )


def _anthropic_factory(settings: Settings) -> LLMProvider | None:
    if not settings.anthropic_api_key:
        logger.info(
            "provider_skipped",
            extra={"provider": "anthropic", "reason": "missing_api_key"},
        )
        return None
    return LitellmChainProvider(
        name="anthropic",
        litellm_model=settings.anthropic_litellm_model_id(),
        api_key=settings.anthropic_api_key,
        timeout_seconds=settings.anthropic_timeout_seconds,
    )


PROVIDER_REGISTRY: dict[str, ProviderFactory] = {
    "openai": _openai_factory,
    "anthropic": _anthropic_factory,
}


def _parse_provider_names(raw_value: str) -> list[str]:
    return [name.strip().lower() for name in raw_value.split(",") if name.strip()]


def build_provider_chain(settings: Settings) -> list[LLMProvider]:
    """Build the ordered provider chain from settings."""

    chain: list[LLMProvider] = []
    for provider_name in _parse_provider_names(settings.llm_providers):
        factory = PROVIDER_REGISTRY.get(provider_name)
        if factory is None:
            logger.warning("provider_unknown", extra={"provider": provider_name})
            continue

        try:
            provider = factory(settings)
        except ProviderConfigError:
            raise

        if provider is not None:
            chain.append(provider)

    if settings.static_fallback_enabled:
        chain.append(StaticFallbackProvider())

    if not chain:
        raise ProviderConfigError(
            "No provider could be configured from LLM_PROVIDERS and static fallback is disabled.",
        )
    return chain
