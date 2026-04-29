"""LLM service and prompt construction tests."""

from dataclasses import dataclass
from typing import Any

import pytest

from app.config import Settings
from app.context.examples import load_examples
from app.services.estimation_engine import EstimationMode
from app.services.llm_service import (
    DomainGuardrailError,
    EstimationError,
    EstimationService,
    build_system_prompt,
)
from app.services.providers.base import (
    ProviderConfigError,
    ProviderInvalidResponseError,
    ProviderResult,
    ProviderTimeoutError,
)


def test_build_system_prompt_includes_both_example_summaries() -> None:
    examples = load_examples()
    prompt = build_system_prompt(examples, EstimationMode.STANDARD)
    assert "Sales KPI dashboard" in prompt
    assert "Service marketplace MVP" in prompt
    assert "Reference estimation examples" in prompt
    assert "only produce estimates for software or project work" in prompt
    assert "Treat requests mentioning software features/components" in prompt
    assert "Adaptive mode: standard" in prompt


@dataclass
class _StubProvider:
    name: str
    model: str
    _result: ProviderResult | None = None
    _error: Exception | None = None
    calls: int = 0

    async def complete(self, system_prompt: str, user_prompt: str) -> ProviderResult:
        del system_prompt
        del user_prompt
        self.calls += 1
        if self._error:
            raise self._error
        assert self._result is not None
        return self._result


def _settings(**overrides: Any) -> Settings:
    defaults = {
        "openai_api_key": "sk-test",
        "anthropic_api_key": "ak-test",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


@pytest.mark.asyncio
async def test_estimate_rejects_empty_transcription() -> None:
    service = EstimationService(_settings(), providers=[])
    with pytest.raises(EstimationError, match="empty"):
        await service.estimate("   ")


@pytest.mark.asyncio
async def test_estimate_rejects_out_of_domain_without_calling_provider() -> None:
    provider = _StubProvider(
        name="openai",
        model="gpt-4o-mini",
        _result=ProviderResult(
            text="## Estimation: should never be used",
            provider="openai",
            model="gpt-4o-mini",
            usage=None,
        ),
    )
    service = EstimationService(_settings(), providers=[provider])
    with pytest.raises(DomainGuardrailError, match="Only software/project estimation"):
        await service.estimate("Que distancia hay desde la tierra al sol?")
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_estimate_allows_out_of_domain_when_guardrail_disabled() -> None:
    provider = _StubProvider(
        name="openai",
        model="gpt-4o-mini",
        _result=ProviderResult(
            text="## Assumptions\n- a\n\n## Tasks\n- b\n\n## Effort summary\n- c",
            provider="openai",
            model="gpt-4o-mini",
            usage=None,
        ),
    )
    service = EstimationService(
        _settings(llm_domain_guardrail_enabled=False),
        providers=[provider],
    )
    result = await service.estimate("Que distancia hay desde la tierra al sol?")
    assert result.provider == "openai"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_estimate_returns_primary_result_without_fallback() -> None:
    primary = _StubProvider(
        name="openai",
        model="gpt-4o-mini",
        _result=ProviderResult(
            text="## Assumptions\n- a\n\n## Estimate range\n- b\n\n## Risks\n- c",
            provider="openai",
            model="gpt-4o-mini",
            usage=None,
        ),
    )
    secondary = _StubProvider(
        name="anthropic",
        model="claude-3-5-haiku-latest",
        _result=ProviderResult(
            text="## Assumptions\n- a\n\n## Estimate range\n- b\n\n## Risks\n- c",
            provider="anthropic",
            model="claude-3-5-haiku-latest",
            usage=None,
        ),
    )
    service = EstimationService(_settings(), providers=[primary, secondary])

    result = await service.estimate("Client needs a portal.")
    assert result.provider == "openai"
    assert result.model == "gpt-4o-mini"
    assert result.mode == EstimationMode.BASIC
    assert primary.calls == 1
    assert secondary.calls == 0


@pytest.mark.asyncio
async def test_estimate_uses_secondary_after_transient_primary_failure() -> None:
    primary = _StubProvider(
        name="openai",
        model="gpt-4o-mini",
        _error=ProviderTimeoutError("timeout"),
    )
    secondary = _StubProvider(
        name="anthropic",
        model="claude-3-5-haiku-latest",
        _result=ProviderResult(
            text="## Assumptions\n- a\n\n## Estimate range\n- b\n\n## Risks\n- c",
            provider="anthropic",
            model="claude-3-5-haiku-latest",
            usage=None,
        ),
    )
    service = EstimationService(_settings(), providers=[primary, secondary])

    result = await service.estimate("Client needs a portal.")
    assert result.provider == "anthropic"
    assert primary.calls == 1
    assert secondary.calls == 1


@pytest.mark.asyncio
async def test_estimate_stops_on_config_error_when_auth_fallback_disabled() -> None:
    primary = _StubProvider(
        name="openai",
        model="gpt-4o-mini",
        _error=ProviderConfigError("OpenAI authentication failed."),
    )
    secondary = _StubProvider(
        name="anthropic",
        model="claude-3-5-haiku-latest",
        _result=ProviderResult(
            text="## Assumptions\n- a\n\n## Estimate range\n- b\n\n## Risks\n- c",
            provider="anthropic",
            model="claude-3-5-haiku-latest",
            usage=None,
        ),
    )
    service = EstimationService(_settings(llm_auth_fallback=False), providers=[primary, secondary])

    with pytest.raises(EstimationError, match="authentication failed"):
        await service.estimate("Client needs a portal.")
    assert primary.calls == 1
    assert secondary.calls == 0


@pytest.mark.asyncio
async def test_estimate_allows_config_error_fallback_when_enabled() -> None:
    primary = _StubProvider(
        name="openai",
        model="gpt-4o-mini",
        _error=ProviderConfigError("OpenAI authentication failed."),
    )
    secondary = _StubProvider(
        name="anthropic",
        model="claude-3-5-haiku-latest",
        _result=ProviderResult(
            text="## Assumptions\n- a\n\n## Estimate range\n- b\n\n## Risks\n- c",
            provider="anthropic",
            model="claude-3-5-haiku-latest",
            usage=None,
        ),
    )
    service = EstimationService(_settings(llm_auth_fallback=True), providers=[primary, secondary])

    result = await service.estimate("Client needs a portal.")
    assert result.provider == "anthropic"
    assert primary.calls == 1
    assert secondary.calls == 1


@pytest.mark.asyncio
async def test_estimate_returns_static_degraded_when_real_providers_fail() -> None:
    failing = _StubProvider(
        name="openai",
        model="gpt-4o-mini",
        _error=ProviderInvalidResponseError("empty"),
    )
    static = _StubProvider(
        name="static_fallback",
        model="static-v1",
        _result=ProviderResult(
            text="## Assumptions\n- a\n\n## Estimate range\n- b\n\n## Risks\n- c",
            provider="static_fallback",
            model="static-v1",
            usage=None,
        ),
    )
    service = EstimationService(_settings(), providers=[failing, static])

    result = await service.estimate("Client needs a portal.")
    assert result.provider == "static_fallback"
    assert result.degraded is True


@pytest.mark.asyncio
async def test_estimate_raises_when_all_providers_fail() -> None:
    providers = [
        _StubProvider(name="openai", model="gpt-4o-mini", _error=ProviderTimeoutError("timeout")),
    ]
    service = EstimationService(_settings(), providers=providers)
    with pytest.raises(EstimationError, match="All providers failed"):
        await service.estimate("Client needs a portal.")


@pytest.mark.asyncio
async def test_estimate_falls_back_when_primary_output_is_structurally_invalid() -> None:
    primary = _StubProvider(
        name="openai",
        model="gpt-4o-mini",
        _result=ProviderResult(
            text="## Estimation: too short",
            provider="openai",
            model="gpt-4o-mini",
            usage=None,
        ),
    )
    secondary = _StubProvider(
        name="anthropic",
        model="claude-3-5-haiku-latest",
        _result=ProviderResult(
            text="## Assumptions\n- a\n\n## Estimate range\n- b\n\n## Risks\n- c",
            provider="anthropic",
            model="claude-3-5-haiku-latest",
            usage=None,
        ),
    )
    service = EstimationService(_settings(), providers=[primary, secondary])

    result = await service.estimate("Client needs a portal.")
    assert result.provider == "anthropic"
    assert primary.calls == 1
    assert secondary.calls == 1


@pytest.mark.asyncio
async def test_estimate_raises_on_unexpected_provider_exception() -> None:
    providers = [
        _StubProvider(name="openai", model="gpt-4o-mini", _error=RuntimeError("boom")),
        _StubProvider(
            name="static_fallback",
            model="static-v1",
            _result=ProviderResult(
                text="## Estimation: degraded",
                provider="static_fallback",
                model="static-v1",
                usage=None,
            ),
        ),
    ]
    service = EstimationService(_settings(), providers=providers)
    with pytest.raises(EstimationError, match="Unexpected provider failure"):
        await service.estimate("Client needs a portal.")
