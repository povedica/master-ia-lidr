# Feature: Langfuse integration (LLM telemetry) — MVP phase

## Objective

Integrate **Langfuse Cloud (EU region)** to **start sending LLM telemetry as soon as possible** (observable traces in Langfuse) with **minimal effort in phase 1**, without blocking later evolution toward **prompt versioning**, **evals**, and **operational dashboards**.

**Why now:** the stack already centralizes calls in `app/services/ai_model_service.py` (LiteLLM) and orchestration in `app/services/llm_service.py` / `app/services/llm_chain.py`, which allows a narrow integration point without redesigning the public API.

## Context

- **Project:** `master-ia` / estimador CAG — FastAPI (`app/routers/estimations.py`), services under `app/services/`, typed settings in `app/config.py` (`pydantic-settings`), variables documented in `.env.example`.
- **Target provider:** Langfuse Cloud EU — typical base `https://cloud.langfuse.com` (project public host in the UI).
- **Credentials:** Project Settings → API Keys → `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`.
- **Host / base URL:** support `LANGFUSE_BASE_URL` and/or `LANGFUSE_HOST` per chosen SDK convention (normalize in `Settings` to one canonical internal value to avoid operational duplication).

## Scope

### Includes (MVP — phase 1)

- **Observable traces** per estimation request (or per “completion” invocation if finer granularity is chosen): latency, model, provider, trace IDs, and **non-sensitive** metadata (for example `app_env`, `estimation_mode`, internal domain error codes).
- **Minimal spans:** one **trace** per HTTP request to `/api/v1/.../estimations` (or equivalent resource) and one **span/generation** tied to the LLM call (summarized or hashed input, summarized or truncated output — see Security).
- **Per-environment configuration:** explicit enablement when valid keys exist or via `LANGFUSE_TRACING_ENABLED` (recommended so local can stay off without deleting keys).
- **Environment variables** documented in `.env.example` and typed in `Settings`.
- **Graceful shutdown:** flush on process exit (FastAPI lifespan / shutdown) to avoid losing spans in short-lived containers.
- **Do not block the hot path:** if Langfuse fails or is disabled, the estimation **must still complete** (silent degradation with structured logging).

### Excludes (phase 1)

- **OpenTelemetry end-to-end** as the sole ingestion path (documented option; see Technical Approach).
- **Prompt management** in Langfuse as the source of truth for prompts (prompts remain in `app/context/` until a later phase).
- Automatic **evals** in Langfuse, datasets, large-scale human annotations.
- **HTTP contract changes** (new mandatory headers for API clients) unless **optional** `trace_id` propagation is added (nice-to-have, not MVP).

## Functional Requirements

1. **Activation:** with `LANGFUSE_TRACING_ENABLED=true` (or agreed policy: “auto ON when secret + public are present”) the backend sends events to Langfuse Cloud EU.
2. **Environment identification:** `environment` metadata or equivalent tag aligned with `APP_ENV` (`local`, `staging`, `prod`, …).
3. **Session / user (pragmatic MVP):**
   - **Session id:** derived from a correlation id if the client sends one in the future; for MVP it may be **optional** or equal to internal `request_id` if it exists; otherwise generate a UUID per request.
   - **User id:** do **not** fabricate identities; if there is no auth, omit or use a fixed `anonymous` only if Langfuse requires it — preferably **omit** until real authentication exists.
4. **Generation payload:** record **usage tokens** when LiteLLM exposes them; prompt/response text **truncated** and/or **hashed** (see Security).
5. **Streamlit / scripts:** same policy; if they call FastAPI, the trace lives in the API. If a script calls the model directly, that is **out of MVP** or an explicit follow-up.

## Technical Approach

### Decision: direct Langfuse SDK vs OpenTelemetry

| Criterion | Langfuse SDK (Python) | OpenTelemetry → Langfuse |
|-----------|------------------------|---------------------------|
| MVP effort | **Low:** initialize client, wrap 1–2 functions, native LLM metadata | **Medium–high:** exporter, resource attrs, generic semantics, possible collector |
| Fit with Langfuse product | **High** (generations, scores, prompts later) | Good if OTEL is already org-wide |
| Vendor lock-in | Langfuse | Lower at transport layer; Langfuse ingest still coupled |
| Non-LLM observability (DB, internal HTTP) | Possible but not the focus | **Better** if OTEL is already used everywhere |

**Recommended decision for phase 1:** **official Langfuse Python SDK** behind a **thin adapter** (for example `app/services/langfuse_tracing.py`) invoked from the LLM domain boundary (`ai_model_service` and/or `EstimationService`), with **zero Langfuse imports** in routers.

**When to reconsider OTEL:** a **corporate collector** exists, **unified traces** (LLM + DB + queues) in one backend are required, or compliance mandates **standard exporters** first. Then evaluate Langfuse’s **documented bridge** (check current docs at implementation time) without rewriting the whole app: keep the same internal adapter boundary.

### Trace / span / session / user model

- **Trace:** one business unit aligned with **one completed or failed estimation** (recommended: estimation handler lifecycle).
- **Span (nested):**
  - Parent span: `estimation.request` (preprocessing, guardrails, prompt construction).
  - Child span / Langfuse **Generation:** `llm.completion` (LiteLLM `acompletion` / aggregated streaming).
- **Session:** optional multi-request grouping; MVP = **one trace per request** without long-lived session unless an explicit header/cookie is added later.
- **User:** reserved for when a stable identity exists (per-tenant API key, JWT, etc.).

### Environment variables and per-environment configuration

Proposal (English names in code and `.env.example`):

| Variable | Purpose |
|----------|---------|
| `LANGFUSE_PUBLIC_KEY` | Project public key |
| `LANGFUSE_SECRET_KEY` | Project secret key |
| `LANGFUSE_BASE_URL` | Langfuse API base URL (e.g. `https://cloud.langfuse.com`) |
| `LANGFUSE_HOST` | **Optional** legacy/docs alias; if both are set, document precedence (`BASE_URL` wins) |
| `LANGFUSE_TRACING_ENABLED` | `true`/`false`; recommended **default false for local** |
| (Optional phase 1.1) `LANGFUSE_SAMPLE_RATE` | Float 0–1 for sampling in staging/prod |

**Per environment:**

- **local:** `LANGFUSE_TRACING_ENABLED=false` by default; empty keys.
- **staging:** `true`, “staging” project keys, `APP_ENV=staging`.
- **prod:** `true`, “prod” project keys, sampling if volume is high.

### Implementation steps (baby steps)

1. Add dependency `langfuse` with `uv add langfuse` (verify exact PyPI package name at implementation time).
2. Extend `Settings` + `.env.example` + `README.md` (observability section) with the variables above and **no real secrets**.
3. Create an **adapter** module with a minimal surface: `start_estimation_trace(...)`, `record_llm_generation(...)`, `end_trace(...)`, `flush()` — real Langfuse implementation behind it.
4. Integrate in **one place** first: `ai_model_service.acomplete_chat` (and streaming equivalent if applicable) to validate data in the Langfuse UI.
5. Raise the span parent from `EstimationService` / estimation engine to include guardrails and mode.
6. FastAPI lifespan: `flush` on shutdown.
7. Tests: **mock** the Langfuse client; assert “generation recorded when enabled” and “not called when disabled”.
8. Document manual verification (see below).

### Reference snippets (Node.js / TypeScript)

> For teams integrating the same Langfuse project from a TypeScript BFF or workers. The Python backend uses its own SDK; keep the **same base URL and keys**.

```typescript
// npm: langfuse
import { Langfuse } from "langfuse";

const langfuse = new Langfuse({
  publicKey: process.env.LANGFUSE_PUBLIC_KEY!,
  secretKey: process.env.LANGFUSE_SECRET_KEY!,
  baseUrl: process.env.LANGFUSE_BASE_URL ?? "https://cloud.langfuse.com",
});

export async function withEstimationTrace<T>(
  name: string,
  fn: (trace: ReturnType<Langfuse["trace"]>) => Promise<T>,
): Promise<T> {
  const trace = langfuse.trace({ name, metadata: { source: "node-bff" } });
  try {
    return await fn(trace);
  } finally {
    await langfuse.flushAsync();
  }
}

// Example: wrap an LLM call
// const generation = trace.generation({
//   name: "chat.completion",
//   model: "gpt-4o-mini",
//   input: [{ role: "user", content: "..." }],
// });
// generation.end({ output: "...", usage: { input: 10, output: 20, total: 30 } });
```

(Python: use the equivalent `langfuse` SDK API — `Langfuse.trace`, `generation`, `flush` — per current documentation.)

## Acceptance Criteria

- [ ] With valid keys and tracing on, each non-streaming estimation produces at least **one trace** visible in Langfuse EU with **model** and **duration**.
- [ ] With tracing off or without keys, the API **returns no errors** and performs **no Langfuse network calls** (or no-op behavior verifiable in tests).
- [ ] `.env.example` and `README` document variables and their purpose.
- [ ] No Langfuse secrets appear in logs, tests, or documentation.
- [ ] Unit tests cover enabled/disabled paths with mocks.

## Test Plan

- **Unit tests:** adapter with injected/fake client; verify metadata construction and SDK exception handling (not propagated to HTTP clients).
- **Integration tests:** optional only if a no-network harness exists (e.g. record payloads to a fake HTTP server); by default **do not** call real Langfuse in CI.
- **Manual checks:**
  - Run `uv run uvicorn app.main:app --reload` with a local `.env` (personal keys **not** committed).
  - Send a sample estimation via API collection or Swagger.
  - Confirm a trace in the Langfuse (EU) UI within 60 seconds and verify prompts/responses do not show policy-forbidden data.

## Documentation Plan

- `README.md`: short “Observability / Langfuse” section.
- This spec (`docs/work-items/feature-009-langfuse-telemetry.md`): canonical MVP scope.
- After implementation: optional brief note in `learnings/docs/sesiones/` if tied to a specific session (personal Spanish voice allowed there per project conventions).

## Validation

- **Smoke:** 1 request → 1 trace + 1 generation.
- **Regression:** `uv run pytest` green without real API keys.
- **Operations:** `APP_ENV` consistent with environment filters in Langfuse (tags/metadata).

## Risks

- **Cardinality / cost:** high event volume in prod → mitigate with **sampling** and metadata limits.
- **Latency:** per-request flush can add milliseconds → use SDK **async/batch** and flush mainly on shutdown plus optional background flush.
- **PII / secrets in prompts:** legal and security risk → truncation, hashing, or omitting full text in MVP.
- **SDK drift:** Langfuse APIs evolve → pin version in `pyproject.toml` and review changelog on minor bumps.

## Security

- Keys only in **environment variables** and deployment secret managers; never in Git.
- **Do not log:** OpenAI/Anthropic API keys, user tokens, unnecessary personal data, full production payloads until retention policy is clear.
- **Network:** HTTPS to `LANGFUSE_BASE_URL`; verify the URL is the agreed **EU** endpoint (avoid typos pointing at another tenant).
- **Least privilege:** separate project keys per environment (staging vs prod).

## Roadmap (post-MVP)

1. **Phase 2 — Prompts:** upload/version prompts from CI or Langfuse UI; link `prompt` id on generations.
2. **Phase 3 — Evals:** automatic scores reusing `estimation_output_validation` / internal metrics; datasets for quality regression.
3. **Phase 4 — Dashboards:** panels by `estimation_mode`, error rate, p95 latency, estimated token cost.
4. **Phase 5 — OTEL (if applicable):** unified exporter behind the same adapter or gradual migration.

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
