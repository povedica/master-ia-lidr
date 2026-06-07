# Actor-Critic-Boss (ACB) orchestration

Online production orchestration for **session estimation quality**. ACB runs only on:

`POST /api/v1/sessions/{session_id}/estimate`

It is **not** applied to metadata extraction, `/api/v1/estimate`, or `/api/v2/estimate`.

## Why three roles

| Role | Responsibility | Output |
| --- | --- | --- |
| **Actor** | Generate the best structured estimate candidate | `EstimationResult` |
| **Critic** | Detect material defects (no rewrite) | `CriticFeedback` |
| **Boss** | Govern the process: accept, one revision, or synthesize | `BossDecision` |

Generation, evaluation, and process governance are separate LLM calls with **structurally different prompts** under `app/prompts/acb/v1/`.

## How it works

```text
SimplifiedSessionEstimationService.run_submit
  → activation: Settings.acb_requested(orchestration override, endpoint=session_estimate)
  → LLMPipeline.run_structured_with_acb (when active)
      → input semantic guardrails (unchanged)
      → skip semantic cache serve (log acb_cache_bypassed)
      → ActorCriticBossOrchestrator.run
          loop (max ACB_MAX_ITERATIONS Actor passes):
            Actor  → EstimationService.estimate_structured (+ revision appendix)
            Critic → complete_structured(CriticFeedback)
            Boss   → complete_structured(BossDecision)
            policy.normalize_boss_decision → ACCEPT | REVISE | SYNTHESIZE
      → output semantic guardrails on **final** EstimationResult only
  → assemble_estimation_v2_response (+ acb_trace when DEV_MODE=true)
```

### Iteration policy (deterministic + Boss LLM)

Pure functions in `app/guardrails/acb/policy.py`:

- **Minor-only issues** → bias ACCEPT
- **Blocking issues** (`ACB_BLOCKING_SEVERITIES`, default `critical,major`) with budget → REVISE (≤5 bullet instructions)
- **Budget exhausted** with blocking issues → SYNTHESIZE (if `ACB_ALLOW_SYNTHESIZE=true`) else ACCEPT best candidate
- Hard cap: `ACB_MAX_ITERATIONS` Actor passes (default `2`)

Boss LLM output is **clamped** by `normalize_boss_decision()` so loops cannot exceed the configured budget.

### Activation (rollout-safe, default off)

| Layer | Setting | Default |
| --- | --- | --- |
| Global | `ACB_ENABLED` | `false` |
| Endpoint allowlist | `ACB_ENABLED_ENDPOINTS` | `session_estimate` |
| Per-request | `SessionEstimateRequest.orchestration` | `null` → follow settings |
| Dev force | `ACB_FORCE_ENABLED_IN_DEV` + `APP_ENV=local` + `DEV_MODE=true` | `false` |

Request overrides:

- `"acb"` — force ACB on allowed endpoint
- `"single_pass"` — force legacy single LLM path (escape hatch)
- `"default"` or omitted — follow settings

### Semantic cache

When ACB is active, **cache serve is bypassed** (`acb_cache_bypassed` log). Intermediate Actor candidates must not be served from cache.

### Observability

Structured logs (stable keys): `acb_orchestration_started`, `acb_actor_completed`, `acb_critic_completed`, `acb_boss_decided`, `acb_orchestration_finished`.

When `OTEL_EXPORT_ENABLED=true` and Langfuse keys are set:

- Parent span: `acb_orchestration`
- Child spans: `acb_actor`, `acb_critic`, `acb_boss`, `acb_synthesize`
- Tags: `feature:session_estimate`, `orchestration:acb`
- Each `complete_structured` call still records `estimator.llm.structured_output` generations nested under the active span

### Dev diagnostics

With `DEV_MODE=true`, `SessionEstimateResponse.estimate.acb_trace` includes iteration summaries (counts, decisions, timings). Production responses (`dev_mode=false`) omit this field.

## Environment variables

See `.env.example` (`ACB_*`). Key fields:

```text
ACB_ENABLED=false
ACB_ENABLED_ENDPOINTS=session_estimate
ACB_MAX_ITERATIONS=2
ACB_ALLOW_SYNTHESIZE=true
ACB_BLOCKING_SEVERITIES=critical,major
ACB_FORCE_ENABLED_IN_DEV=false
ACB_CRITIC_MODEL=
ACB_BOSS_MODEL=
ACB_PROMPT_VERSION=v1
```

Empty `ACB_CRITIC_MODEL` / `ACB_BOSS_MODEL` fall back to `OPENAI_MODEL`.

## Local testing

### Automated (no API keys)

```bash
uv run pytest tests/test_acb_schemas.py tests/test_acb_policy.py \
  tests/test_acb_orchestrator.py tests/test_acb_prompt_rendering.py -q

# Integration (requires SESSION_INTEGRATION_TEST_USE_REAL_LLM=false)
uv run pytest tests/test_sessions_acb_integration.py -q
```

### Manual with real provider

```bash
# .env
ACB_ENABLED=true
ACB_FORCE_ENABLED_IN_DEV=true
DEV_MODE=true
APP_ENV=local
OPENAI_API_KEY=sk-...

uv run uvicorn app.main:app --reload
```

Submit a session estimate (UI or curl). Expect ~3+ LLM calls per request when Critic and Boss run. Inspect `estimate.acb_trace` in JSON when `DEV_MODE=true`.

Compare latency with ACB off (`ACB_ENABLED=false`) on the same transcript.

### Per-request override (curl)

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/sessions/<session_id>/estimate" \
  -H "Content-Type: application/json" \
  -d '{"transcript":"...", "project_name":"Demo", "project_type":"web_saas", "target_audience":"b2b_smb", "orchestration":"acb"}'
```

Force single-pass: `"orchestration":"single_pass"`.

## Anti-patterns

1. Same prompt for all three roles
2. Critic that rewrites the estimate
3. Boss that re-runs full Critic analysis
4. ACB on metadata extraction or every LLM call
5. Unbounded revision loops (always enforce `ACB_MAX_ITERATIONS` in code)
6. Serving semantic cache hits during orchestration
7. Output guardrails on intermediate Actor candidates

## Related docs

- Canonical feature spec: `docs/work-items/feature-026-actor-critic-boss-estimation-orchestration.md`
- Interactive architecture: `docs/arquitectura-estimador-cag.html#acb`
- Offline quality evals (not production Boss logic): `docs/evals/session-estimation-evals.md`
