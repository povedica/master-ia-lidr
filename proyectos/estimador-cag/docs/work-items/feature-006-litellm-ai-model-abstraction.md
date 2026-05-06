# Feature: LiteLLM as the AI model abstraction layer

## Objective

Add **LiteLLM** as the single gateway for chat completions so the application does not depend on provider-specific SDKs in business logic. Model identity and credentials remain **configuration-driven**, so switching providers (OpenAI, Anthropic, Google Gemini, etc.) is done by changing environment/settings, not application code.

## Context

- **Project:** `proyectos/estimador-cag` — FastAPI + optional Streamlit; `uv` + `pyproject.toml` (not `requirements.txt`).
- **Existing architecture (keep boundaries):**
  - `app/services/llm_service.py` — `EstimationService` orchestrates preprocessing and an ordered **provider chain**.
  - `app/services/providers/` — `LLMProvider` protocol, `ProviderResult`, typed `ProviderError` subclasses.
  - `app/services/providers/openai_provider.py` — uses **AsyncOpenAI** directly.
  - `app/services/providers/anthropic_provider.py` — uses **Anthropic** SDK directly.
  - `app/services/providers/__init__.py` — builds chain from `LLM_PROVIDERS` (CSV); skips missing keys; optional static fallback.
  - `app/config.py` — `openai_*`, `anthropic_*`, timeouts; no Gemini key today.
- **Related doc:** `feature-llm-provider-fallback.md` describes the current chain behavior; this feature **replaces transport** with LiteLLM while preserving the chain contract unless explicitly revised in implementation.
- **Async:** Route handlers and providers are **async**; LiteLLM should use **`acompletion`** (or equivalent async API), not blocking `completion` in the hot path.

## Scope

### Includes

- Add **`litellm`** to dependencies via `uv add litellm` (keep existing packages unless a follow-up explicitly removes redundant SDKs).
- Introduce **`app/services/ai_model_service.py`** as the **only** module that imports `litellm` and performs completion calls.
- Refactor **`OpenAIProvider`** and **`AnthropicProvider`** (and any other real providers) to delegate completions to `ai_model_service`; **no** `litellm` imports in routers, `llm_service.py`, or Streamlit.
- Extend **`Settings`** and **`.env.example`** for:
  - A **canonical default model** suitable for LiteLLM (`provider/model` form), e.g. `openai/gpt-4o-mini`.
  - Optional explicit **default LLM provider** label for logging/routing (must not duplicate secrets).
  - **`GEMINI_API_KEY`** (and any other keys needed for chosen providers), documented as optional until a provider is wired.
- **Provider switching by config:** same runtime code path; model string follows LiteLLM conventions (`openai/...`, `anthropic/...`, `gemini/...`).
- **Normalized response** from the service layer: at minimum `content`, `model`, optional **`usage`** (`prompt_tokens`, `completion_tokens`, `total_tokens`) when LiteLLM returns usage.
- **Error handling:** map LiteLLM/provider failures into existing **`ProviderError`** types where possible; never return raw provider payloads to HTTP/Streamlit users. Cover missing key, bad model id, rate limit, quota, timeout, and unexpected errors.
- **Structured logging:** request start, success, failure with `model`, inferred provider, `error_type`; **never** log API keys, secrets, or full prompts/responses.

### Excludes

- LiteLLM proxy server deployment.
- Advanced routing, fallback chains **beyond** the existing `LLM_PROVIDERS` chain (unless merged carefully in a follow-up).
- Embeddings, image models, streaming, RAG, multi-agent orchestration.
- Persistent cost DB or dashboards.
- Removing `openai` / `anthropic` packages immediately — optional follow-up once LiteLLM path is verified.

## Functional requirements

### FR-1 Dependency

- Add `litellm` to `pyproject.toml` with a compatible version range; run `uv lock` and commit `uv.lock`.

### FR-2 Single LiteLLM module

- **`app/services/ai_model_service.py`** exposes documented async functions (e.g. complete chat from system + user messages) that call **`litellm.acompletion`** with `model` and timeout from settings.
- All LiteLLM usage stays in this module.

### FR-3 Settings

- No hardcoded model names, base URLs, or API keys in service logic.
- Support at least:
  - **`DEFAULT_LLM_PROVIDER`** (string; for logs / defaults where needed).
  - **`DEFAULT_LLM_MODEL`** (LiteLLM model id, e.g. `openai/gpt-4o-mini`).
  - **`OPENAI_API_KEY`**, **`ANTHROPIC_API_KEY`**, **`GEMINI_API_KEY`** (optional empty strings / optional fields as per existing patterns).
- **Migration story:** either keep **`OPENAI_MODEL`** / **`ANTHROPIC_MODEL`** and derive `openai/{OPENAI_MODEL}` inside the provider, **or** document a single-session env migration to `DEFAULT_LLM_MODEL` + chain — pick one approach in implementation notes and update `.env.example` accordingly.

### FR-4 Provider chain compatibility

- Preserve **`LLM_PROVIDERS`** ordering and skip-if-unconfigured behavior.
- Each chain entry that represents a backend must ultimately call **`ai_model_service`** (not SDKs directly).

### FR-5 Streamlit and FastAPI

- **`app/streamlit_app.py`** and **`app/routers/estimations.py`** continue to use **`EstimationService`** / existing dependencies; they must not import LiteLLM.

### FR-6 Usage metadata

- When the LiteLLM response includes usage, propagate into **`ProviderResult.usage`** / **`UsageInfo`** consistently.

## Technical approach

1. **Add dependency:** `cd proyectos/estimador-cag && uv add litellm`.
2. **Settings:** extend `app/config.py` with `default_llm_provider`, `default_llm_model`, `gemini_api_key` (and timeouts if LiteLLM needs global timeout — align with existing `*_timeout_seconds` or a dedicated `llm_request_timeout_seconds`).
3. **Environment:** update **`proyectos/estimador-cag/.env.example`** and **`README.md` / `docs/technical/README.md`** with new variables and LiteLLM model string examples.
4. **`ai_model_service.py`:**
   - Async completion helper(s) with explicit parameters: `model`, `messages`, `max_tokens` (or LiteLLM’s equivalent), timeout.
   - Map LiteLLM exceptions to **`ProviderTimeoutError`**, **`ProviderUnavailableError`**, **`ProviderInvalidResponseError`**, **`ProviderConfigError`** as appropriate.
   - Structured logging with stable **`extra` keys** (e.g. `llm_request_started`, `llm_request_succeeded`, `llm_request_failed`).
5. **Refactor providers:** `OpenAIProvider` / `AnthropicProvider` call `ai_model_service` with the correct **`model`** string per settings; remove direct SDK usage from those modules.
6. **Tests:** mock **`litellm.acompletion`** (or the thin wrapper in `ai_model_service`) — no real API keys in default suite.

## Acceptance criteria

- [ ] `litellm` is listed in `pyproject.toml` and locked in `uv.lock`.
- [ ] `app/services/ai_model_service.py` exists and is the sole LiteLLM import site.
- [ ] **`OpenAIProvider` and `AnthropicProvider` do not import `openai` / `anthropic` SDKs** for completions (optional: SDK deps remain installed until removed in a follow-up).
- [ ] `DEFAULT_LLM_MODEL` and keys are read from settings/env; no secrets or model ids hardcoded in business logic.
- [ ] Switching **`DEFAULT_LLM_MODEL`** (e.g. to `anthropic/claude-3-5-haiku-latest`) works **without code changes** where the chain/provider configuration points at that model.
- [ ] Errors are mapped to safe messages for API/Streamlit; no raw provider errors exposed.
- [ ] Logging covers start/success/failure with model and error class; no secrets or full prompts/responses logged.
- [ ] Responses include usage when LiteLLM returns it, mapped into existing types.
- [ ] `uv run pytest` passes without real keys.
- [ ] `.env.example` and technical docs updated.

## Test plan

### Unit

- `ai_model_service`: maps exceptions to the right `ProviderError` types; parses content and usage from a mocked LiteLLM response; empty prompt/message validation if enforced.
- `OpenAIProvider` / `AnthropicProvider`: with mocked `acompletion`, returns `ProviderResult` consistent with today’s contract.

### Integration (light)

- `EstimationService.estimate` with mocked provider chain (existing patterns) still returns structured results.

### Manual

- `uv run uvicorn app.main:app --reload` — health and one estimate with valid key (operator’s machine).
- `uv run streamlit run app/streamlit_app.py` — one successful request path.

## Documentation plan

- **`proyectos/estimador-cag/.env.example`** — new variables and examples for LiteLLM model ids.
- **`proyectos/estimador-cag/README.md`** — how to set `DEFAULT_LLM_MODEL` and provider keys.
- **`proyectos/estimador-cag/docs/technical/README.md`** — architecture note: LiteLLM gateway, file map, logging keys.
- Optional: sync Second Brain via `bash scripts/sync-estimador-cag-docs.sh` if vault mirrors this work item.

## Baby steps and verification

1. Add `litellm` + lockfile; **`uv run python -c "import litellm"`** smoke test.
2. Add settings + `.env.example` only; load settings in a tiny test or REPL.
3. Implement `ai_model_service` + unit tests with mocks.
4. Refactor one provider (e.g. OpenAI), run targeted tests, then second provider.
5. Full `uv run pytest`; manual API/Streamlit smoke.
6. Update docs; mark acceptance checklist.

**Verified in spec:** N/A (planning only).  
**Not verified:** Runtime behavior until implemented.

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `5d845bf` | `docs(estimador-cag): add feature-006 LiteLLM work item` | Planning/spec work item for LiteLLM gateway; no runtime code in this commit. |

### Planned implementation commits (not in git yet)

Example messages for upcoming rows (adjust when implemented):

1. `feat(estimador-cag): add litellm dependency and ai_model_service scaffold`
2. `refactor(estimador-cag): route OpenAI/Anthropic providers through LiteLLM`
3. `docs(estimador-cag): document DEFAULT_LLM_MODEL and Gemini env vars`
