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
from app.services.llm_types import (
    ProviderConfigError,
    ProviderInvalidResponseError,
    ProviderResult,
    ProviderTimeoutError,
    UsageInfo,
)


def test_build_system_prompt_includes_inline_cleaning_when_enabled() -> None:
    examples = load_examples()
    prompt = build_system_prompt(examples, EstimationMode.STANDARD, inline_cleaning=True)
    assert "Extract ONLY the functional" in prompt


def test_build_system_prompt_includes_both_example_summaries() -> None:
    examples = load_examples()
    prompt = build_system_prompt(examples, EstimationMode.STANDARD)
    assert len(examples) >= 2
    assert "Reference estimation examples" in prompt
    assert "Historical estimation sample" in prompt
    assert "Example 1 — meeting summary" in prompt
    assert "estimation profile (routing): standard" in prompt.lower()
    assert "practical estimation" in prompt.lower()
    assert "simulated role rate card" in prompt.lower()


@dataclass
class _StubProvider:
    name: str
    model: str
    _result: ProviderResult | None = None
    _error: Exception | None = None
    calls: int = 0
    last_max_output_tokens: int | None = None

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_output_tokens: int,
    ) -> ProviderResult:
        del system_prompt
        del user_prompt
        self.last_max_output_tokens = max_output_tokens
        self.calls += 1
        if self._error:
            raise self._error
        assert self._result is not None
        return self._result


def _settings(**overrides: Any) -> Settings:
    defaults = {
        "openai_api_key": "sk-test",
        "anthropic_api_key": "ak-test",
        "llm_auth_fallback": False,
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

    transcription = "Client needs a portal."
    result = await service.estimate(transcription)
    assert result.provider == "openai"
    assert result.model == "gpt-4o-mini"
    assert result.mode == EstimationMode.BASIC
    assert result.assessment is not None
    assert result.assessment.recommended_mode == EstimationMode.BASIC
    assert result.mode_eligibility is not None
    assert EstimationMode.BASIC in result.mode_eligibility.allowed_modes
    assert primary.calls == 1
    assert secondary.calls == 0
    assert primary.last_max_output_tokens == 1024


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
async def test_estimate_downgrades_expert_review_when_input_quality_is_low() -> None:
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
    service = EstimationService(_settings(), providers=[provider])

    result = await service.estimate(
        "Maybe we need something like a platform, not sure yet, whatever works."
    )
    assert result.assessment is not None
    assert result.assessment.recommended_mode == EstimationMode.EXPERT_REVIEW
    assert result.mode == EstimationMode.STANDARD
    assert result.mode_eligibility is not None
    assert EstimationMode.EXPERT_REVIEW in result.mode_eligibility.blocked_modes
    assert result.mode_eligibility.reason == "Input detail is insufficient."


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
async def test_two_phase_preprocessing_merges_phase_one_tokens() -> None:
    valid = "## Assumptions\n- a\n\n## Estimate range\n- b\n\n## Risks\n- c\n"
    extraction = "- requirement one\n- requirement two\n"

    class _TwoPhaseStub:
        name = "openai"
        model = "gpt-4o-mini"
        calls = 0

        async def complete(
            self,
            system_prompt: str,
            user_prompt: str,
            *,
            max_output_tokens: int,
        ) -> ProviderResult:
            del user_prompt
            self.calls += 1
            if "analyst" in system_prompt.lower():
                return ProviderResult(
                    text=extraction,
                    provider="openai",
                    model="gpt-4o-mini",
                    usage=UsageInfo(9, 4, 13, 0, 0),
                    finish_reason="stop",
                )
            return ProviderResult(
                text=valid,
                provider="openai",
                model="gpt-4o-mini",
                usage=UsageInfo(80, 40, 120, 1, 1),
                finish_reason="stop",
            )

    stub = _TwoPhaseStub()
    service = EstimationService(_settings(), providers=[stub])
    result = await service.estimate("Client needs a portal with API.", preprocessing="two_phase")
    assert stub.calls == 2
    assert result.estimation == valid
    assert result.usage is not None
    assert result.usage.preprocessing_input_tokens == 10
    assert result.usage.preprocessing_output_tokens == 5


@pytest.mark.asyncio
async def test_estimate_raises_on_unexpected_provider_exception() -> None:
    providers = [
        _StubProvider(name="openai", model="gpt-4o-mini", _error=RuntimeError("boom")),
    ]
    service = EstimationService(_settings(), providers=providers)
    with pytest.raises(EstimationError, match="Unexpected provider failure"):
        await service.estimate("Client needs a portal.")


def test_serialize_sse_event_returns_valid_payload() -> None:
    payload = EstimationService.serialize_sse_event("chunk", {"content": "hello"})
    assert payload == 'event: chunk\ndata: {"content":"hello"}\n\n'


@pytest.mark.asyncio
async def test_stream_estimation_emits_done_event() -> None:
    provider = _StubProvider(
        name="openai",
        model="gpt-4o-mini",
        _result=ProviderResult(
            text="## Assumptions\n- a\n\n## Estimate range\n- b\n\n## Risks\n- c",
            provider="openai",
            model="gpt-4o-mini",
            usage=None,
        ),
    )
    service = EstimationService(_settings(), providers=[provider])

    events = [event async for event in service.stream_estimation("Client needs a portal.")]
    assert any("event: chunk" in event for event in events)
    assert events[-1].startswith("event: done\n")
    assert '"status":"completed"' in events[-1]


@pytest.mark.asyncio
async def test_stream_estimation_done_includes_usage_when_dev_mode_and_upstream_reports() -> None:
    provider = _StreamingStubProvider(
        name="openai",
        model="gpt-4o-mini",
        _deltas=["## ok\n"],
        _final_usage=UsageInfo(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            preprocessing_input_tokens=0,
            preprocessing_output_tokens=0,
        ),
    )
    service = EstimationService(_settings(dev_mode=True), providers=[provider])

    events = [event async for event in service.stream_estimation("Client needs a portal.")]
    assert events[-1].startswith("event: done\n")
    assert '"usage"' in events[-1]
    assert '"prompt_tokens":10' in events[-1]
    assert '"completion_tokens":5' in events[-1]


@pytest.mark.asyncio
async def test_stream_estimation_emits_error_event_on_failure() -> None:
    provider = _StubProvider(
        name="openai",
        model="gpt-4o-mini",
        _error=ProviderTimeoutError("timeout"),
    )
    service = EstimationService(_settings(), providers=[provider])

    events = [event async for event in service.stream_estimation("Client needs a portal.")]
    assert len(events) == 1
    assert events[0] == 'event: error\ndata: {"message":"All providers failed."}\n\n'


@dataclass
class _StreamingStubProvider:
    """Provider stub that emits pre-configured deltas through `stream_complete`.

    If `_final_usage` is set, it is yielded after all text deltas (mirrors live providers).

    If `_stream_error` is set, it is raised after yielding all configured deltas
    (simulating a mid-stream upstream failure that drops the connection partway).
    """

    name: str
    model: str
    _deltas: list[str]
    _stream_error: Exception | None = None
    _final_usage: UsageInfo | None = None
    last_max_output_tokens: int | None = None

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_output_tokens: int,
    ) -> ProviderResult:
        del system_prompt, user_prompt, max_output_tokens
        raise AssertionError("stream-capable provider must use stream_complete in tests.")

    async def stream_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_output_tokens: int,
    ):
        del system_prompt
        del user_prompt
        self.last_max_output_tokens = max_output_tokens
        for delta in self._deltas:
            yield delta
        if self._stream_error is not None:
            raise self._stream_error
        if self._final_usage is not None:
            yield self._final_usage


@pytest.mark.asyncio
async def test_stream_estimation_emits_one_chunk_event_per_upstream_delta() -> None:
    provider = _StreamingStubProvider(
        name="openai",
        model="gpt-4o-mini",
        _deltas=["## Assumptions\n", "- a\n\n", "## Estimate range\n", "- b"],
    )
    service = EstimationService(_settings(), providers=[provider])

    events = [event async for event in service.stream_estimation("Client needs a portal.")]
    chunk_events = [event for event in events if event.startswith("event: chunk")]
    assert len(chunk_events) == 4
    assert chunk_events[0] == 'event: chunk\ndata: {"content":"## Assumptions\\n"}\n\n'
    assert chunk_events[3] == 'event: chunk\ndata: {"content":"- b"}\n\n'
    assert events[-1].startswith("event: done\n")
    assert '"status":"completed"' in events[-1]


@pytest.mark.asyncio
async def test_stream_estimation_emits_chunks_progressively_not_in_burst() -> None:
    """Verifies SSE chunks are yielded as deltas arrive, not buffered until done."""

    provider = _StreamingStubProvider(
        name="openai",
        model="gpt-4o-mini",
        _deltas=["one ", "two ", "three"],
    )
    service = EstimationService(_settings(), providers=[provider])

    chunks_seen: list[str] = []
    saw_done = False
    async for event in service.stream_estimation("Client needs a portal."):
        if event.startswith("event: chunk"):
            # Each delta must surface before the next iteration of the upstream stream;
            # if the implementation buffered the full output, all chunk events would
            # only appear after the `done` event (which never arrives mid-iteration).
            chunks_seen.append(event)
        elif event.startswith("event: done"):
            saw_done = True
            assert len(chunks_seen) == 3, (
                "done event must follow all chunk events emitted progressively"
            )

    assert saw_done is True
    assert len(chunks_seen) == 3


@pytest.mark.asyncio
async def test_stream_estimation_falls_back_to_next_provider_on_mid_stream_failure() -> None:
    failing = _StreamingStubProvider(
        name="openai",
        model="gpt-4o-mini",
        _deltas=["partial "],
        _stream_error=ProviderTimeoutError("upstream dropped"),
    )
    healthy = _StreamingStubProvider(
        name="anthropic",
        model="claude-haiku",
        _deltas=["full ", "answer"],
    )
    service = EstimationService(_settings(), providers=[failing, healthy])

    events = [event async for event in service.stream_estimation("Client needs a portal.")]
    chunk_events = [event for event in events if event.startswith("event: chunk")]
    # Both partial chunk from failing provider AND complete chunks from healthy provider are emitted.
    assert any('"content":"partial "' in event for event in chunk_events)
    assert any('"content":"full "' in event for event in chunk_events)
    assert any('"content":"answer"' in event for event in chunk_events)
    assert events[-1].startswith("event: done\n")
    assert '"status":"completed"' in events[-1]


@pytest.mark.asyncio
async def test_stream_estimation_uses_complete_for_non_streaming_provider() -> None:
    """Static fallback (no `stream_complete`) must be invoked via `complete()` and emit one chunk."""

    fallback = _StubProvider(
        name="static_fallback",
        model="static-v1",
        _result=ProviderResult(
            text="## Estimation: Temporary degraded mode\n- placeholder",
            provider="static_fallback",
            model="static-v1",
            usage=None,
        ),
    )
    service = EstimationService(_settings(), providers=[fallback])

    events = [event async for event in service.stream_estimation("Client needs a portal.")]
    chunk_events = [event for event in events if event.startswith("event: chunk")]
    assert len(chunk_events) == 1
    assert "Temporary degraded mode" in chunk_events[0]
    assert events[-1].startswith("event: done\n")
    assert '"status":"completed"' in events[-1]


@pytest.mark.asyncio
async def test_stream_estimation_emits_error_when_domain_guardrail_rejects() -> None:
    provider = _StreamingStubProvider(
        name="openai",
        model="gpt-4o-mini",
        _deltas=["should not be emitted"],
    )
    service = EstimationService(
        _settings(llm_domain_guardrail_enabled=True),
        providers=[provider],
    )

    events = [event async for event in service.stream_estimation("Tell me a joke.")]
    assert len(events) == 1
    assert events[0].startswith("event: error")
    assert "estimation requests" in events[0]
