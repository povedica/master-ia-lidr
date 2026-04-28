# Feature: LLM provider fallback chain

## Objective

Add a provider abstraction and ordered fallback chain so `estimador-cag` can recover from transient LLM failures while keeping clear operational signals for configuration errors.

## Context

- `app/services/llm_service.py` is hardcoded to OpenAI (`if self._settings.llm_provider.lower() != "openai"`).
- `app/config.py` already defines `anthropic_api_key` and `anthropic_model`, but they are not used.
- `app/routers/estimations.py` currently returns `provider="openai"` and `model=settings.openai_model` regardless of the real backend path.
- Cost estimation only has pricing for `gpt-4o-mini` in `_MODEL_COSTS_PER_1M_TOKENS`.

## Scope

### Includes

- Provider abstraction in `app/services/providers/` with a minimal protocol and typed provider errors.
- Ordered provider chain configured by `LLM_PROVIDERS`.
- Optional static fallback provider as last resort.
- Dynamic `provider` and `model` in API responses.
- `degraded=true` when static fallback is used.
- Startup fail-fast if provider chain is empty.
- Structured logs for attempts, failures, skips, and degraded behavior.

### Excludes

- Retry/backoff logic.
- Global chain timeout.
- Streaming/tool-calling/vision.
- Anthropic pricing integration (`estimated_cost_usd` remains `null` when pricing is unknown).
- Metrics stack (Prometheus/OpenTelemetry).
- Provider-specific prompt versions.
- Client caching/pooling changes.

## Functional Requirements

- **FR-1**: Build provider chain from `LLM_PROVIDERS` (ordered CSV).
- **FR-2**: Skip unconfigured providers with explicit log signal.
- **FR-3**: Add optional static fallback (`STATIC_FALLBACK_ENABLED`).
- **FR-4**: Map provider errors into:
  - `ProviderTimeoutError`
  - `ProviderUnavailableError`
  - `ProviderInvalidResponseError`
  - `ProviderConfigError`
- **FR-5**: `ProviderConfigError` does not fallback by default; fallback only when `LLM_AUTH_FALLBACK=true`.
- **FR-6**: Router returns actual `provider` and `model`; include `degraded=true` only for static fallback responses.
- **FR-7**: Application startup fails with actionable error when no provider can be built and static fallback is disabled.

## Acceptance Criteria

- [ ] With valid OpenAI credentials, `POST /api/v1/estimate` returns `provider="openai"` and no `degraded`.
- [ ] With invalid OpenAI credentials and `LLM_AUTH_FALLBACK=false`, endpoint returns `503` with safe auth/config message.
- [ ] With missing OpenAI key and valid Anthropic key, OpenAI is skipped and response uses `provider="anthropic"`.
- [ ] With timeout on OpenAI and available Anthropic, response falls back to Anthropic.
- [ ] With all real providers unavailable and `STATIC_FALLBACK_ENABLED=true`, response is `200`, `provider="static_fallback"`, `degraded=true`.
- [ ] With all real providers unavailable and `STATIC_FALLBACK_ENABLED=false`, endpoint returns `503`.
- [ ] If no provider can be built at startup and static fallback is disabled, app startup fails fast.
- [ ] Test suite passes without real provider API keys.
- [ ] `.env.example`, `README.md`, and `docs/technical/README.md` are updated consistently.

## Test Plan

### Unit

- `OpenAIProvider` error mapping and empty-response handling.
- `AnthropicProvider` error mapping and SDK call shape (`system` as top-level field).
- `StaticFallbackProvider` output shape and metadata.
- Provider-chain builder ordering, skipping, unknown names, and empty-chain behavior.
- `EstimationService` chain behavior for success, fallback, config error policy, degraded fallback, and full exhaustion.

### API

- Response contract reflects dynamic provider/model and optional `degraded`.
- Usage stays hidden when `DEV_MODE=false`.
- Static fallback responses omit `usage` even when `DEV_MODE=true`.

### Manual

- Run local API and validate scenarios for: primary success, auth 503, secondary fallback, static degraded fallback, and startup fail-fast case.

## Documentation Plan

- Update:
  - `.env.example`
  - `README.md`
  - `docs/technical/README.md`
- Keep this work-item as the canonical implementation record.

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|---|---|---|
| `c0deb96` | `feat(services): add provider chain abstraction and fallback backends` | Add provider modules (OpenAI, Anthropic, static fallback), refactor service orchestration, and introduce provider-chain settings/dependency updates. |
| `ecd3aff` | `feat(api): add provider-aware estimation schemas and startup checks` | Extract HTTP schemas, wire provider-aware API responses, and enforce provider-chain validation at startup. |
| `18534af` | `test(estimador-cag): expand fallback coverage across providers and API` | Cover provider error mapping, chain ordering, degraded responses, auth fallback policy, and updated request/response contracts. |
| `84ba109` | `docs(estimador-cag): document provider fallback contracts and verification` | Update README/technical docs and add the canonical work-item for this feature implementation. |

