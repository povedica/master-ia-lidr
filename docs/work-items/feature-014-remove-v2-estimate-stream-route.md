# Technical spec: replace `POST /api/v2/estimate/stream` with `POST /api/v2/estimate`

## 1. Executive summary

Use `POST /api/v2/estimate` as the primary route for structured estimation from the Estimador CAG web form instead of `POST /api/v2/estimate/stream`.

The `/stream` suffix no longer matches behavior: the endpoint does not deliver progressive updates or content chunks; at most it emits a single terminal `done` SSE event with the final structured result. The path name therefore describes behavior that no longer exists.

Expected impact:

- Clearer API aligned with reality: synchronous HTTP request and final JSON response.
- Simpler frontend: normal `fetch` with `application/json`, no SSE parser on the main path.
- Less semantic debt in docs, tests, logs, and maintenance.
- A controlled transition to find remaining `/stream` consumers before removal.

**Assumption:** `POST /api/v2/estimate` already exists or will be implemented as the canonical non-streaming structured path equivalent to current behavior.

## 2. Current problem

`/stream` is misleading because it implies streaming output, but the system no longer delivers incremental progress or partial tokens. The web client sends form parameters and expects a single structured result; keeping `/stream` forces a false transport abstraction in the client and in documentation.

Risks of keeping a misleading name:

- New clients may add unnecessary SSE handling expecting `chunk`, `done`, or reconnection logic.
- Operators may debug under wrong assumptions (e.g. “streaming latency” when the flow is effectively one-shot).
- Public or internal API docs diverge from the real **HTTP** contract.
- Accidental frontend complexity persists: SSE parser, manual `ReadableStream` reads, chunk accumulation, `doneMeta` state.
- Contract evolution is harder because the path is tied to a transport technique that no longer applies.

## 3. Functional goal

The canonical endpoint must accept the same parameters the Estimador CAG web form sends today.

It must behave as **synchronous / non-streaming at the HTTP boundary**: one HTTP request, one final HTTP response.

It must return structured JSON for the estimation, including the `result` object and v2 metadata where applicable: `request_id`, `latency_ms`, `final_status`, `reason_code`, `usage`, `cached`, `cache_score`, and related fields.

**Assumption:** Internally, generation may still use async LLM calls, guardrails, and semantic cache. “Synchronous / non-streaming” refers to the **HTTP contract** observed by the client, not necessarily every internal await.

## 4. Proposed API design

**Final path**

- `POST /api/v2/estimate`

**HTTP method**

- `POST`

**Content-Type**

- Request: `application/json`
- Successful response: `application/json`

**Request body**

Reuse the guided-form contract modeled by `EstimationRequest`.

Illustrative example:

```json
{
  "project_name": "B2B partner portal",
  "project_summary": "B2B portal for partners to submit requests and track SLA status.",
  "project_type": "web_saas",
  "target_audience": "b2b_smb",
  "target_audience_other": null,
  "industry": "generic_b2b",
  "industry_other": null,
  "project_description": "Authenticated partners create requests, attach basic information, view status, receive notifications, and browse case history with operational traceability.",
  "deliverables": [
    "Request intake form",
    "SLA tracking dashboard",
    "Email notifications"
  ],
  "out_of_scope": ["Native mobile app"],
  "delivery_urgency": "standard",
  "target_date": null,
  "delivery_approach": "mvp_then_iterate",
  "integration_categories": ["email_notifications", "identity_sso"],
  "integration_custom_names": null,
  "data_sensitivity": "internal_business",
  "hosting_constraints": ["cloud_managed"],
  "hosting_notes": null,
  "team_context": "vendor_led",
  "ui_languages": ["es"],
  "risk_level": "medium",
  "external_dependencies": ["Corporate SSO provider"],
  "detail_level": "medium",
  "output_format": "phases_table",
  "attachments": [],
  "preprocessing": "none",
  "evaluate": true
}
```

**Response body**

Return the `EstimationResponse` contract, with `result` as the primary business payload.

Illustrative example:

```json
{
  "result": {
    "schema_version": "1",
    "title": "Estimate for B2B partner portal",
    "summary": "Web MVP to register requests, show SLA status, and send notifications.",
    "phases": [
      {
        "name": "Discovery and functional design",
        "items": [
          {
            "name": "Requirements alignment and core flows",
            "category": "discovery",
            "hours": 16,
            "cost_eur": 1200
          }
        ]
      }
    ],
    "line_items": [],
    "totals": {
      "hours": 16,
      "cost_eur": 1200
    },
    "duration_weeks": 2,
    "confidence": 0.74,
    "assumptions": ["SSO vendor provides documentation and a test environment on time."],
    "risks": ["External dependency on the SSO vendor."],
    "recommended_team": ["Backend engineer", "Frontend engineer", "Product designer"],
    "human_summary": "Viable MVP with medium complexity due to SSO integration.",
    "presentation": {
      "format": "phases_table"
    }
  },
  "prompt_version": "v5",
  "examples_version": "file-mode-v3",
  "mode": "full",
  "model": "gpt-4o-mini",
  "provider": "openai",
  "request_id": "est_abc123def456",
  "latency_ms": 8421,
  "degraded": false,
  "score": 1,
  "final_status": "success",
  "reason_code": null,
  "user_message": null,
  "audit_id": "audit_abc123",
  "safe_to_cache": true,
  "safe_to_display": true,
  "cached": false,
  "cache_score": null,
  "cache_bucket": null,
  "cache_miss_reason": "miss"
}
```

**Status codes**

- `200 OK`: estimation completed or safe degraded response; use `final_status` for functional state.
- `422 Unprocessable Content`: invalid request from Pydantic validation or blocking input guardrail.
- `503 Service Unavailable`: LLM provider, structured pipeline, optional persistence, or internal dependency unavailable.
- `500 Internal Server Error`: unexpected failure. Log with safe context; do not leak internals to clients.

Illustrative route signature:

```python
@router.post("/estimate", response_model=EstimationResponse, response_model_exclude_none=True)
async def create_estimate_structured(body: EstimationRequest) -> EstimationResponse:
    ...
```

## 5. Compatibility and migration

The web client must stop calling `/api/v2/estimate/stream` and call `/api/v2/estimate`. Migration includes switching `Accept: text/event-stream` to `Accept: application/json` and replacing incremental body reads with `await response.json()` (or equivalent).

**Compatibility options**

- **Option A — temporary `/stream` alias:** keep `POST /api/v2/estimate/stream` for a short window, delegating internally to the same code path as `/estimate` or returning an equivalent single payload. Emit per-request deprecation logs.
- **Option B — HTTP redirect:** not recommended for `POST`; body handling across clients, proxies, and browsers is inconsistent.
- **Option C — direct removal:** simplest long-term, risky if unknown consumers, scripts, stale deployments, or docs still reference `/stream`.

**Recommendation**

Keep `POST /api/v2/estimate/stream` as a **temporary deprecated alias** during a short, observable window. This limits operational risk, allows the web migration first, and surfaces real remaining traffic. Avoid HTTP redirects for this case.

**Phased plan**

- **Phase 0 — prep:** document `/api/v2/estimate` as canonical; mark `/api/v2/estimate/stream` deprecated in README, technical docs, and OpenAPI if still exposed.
- **Phase 1 — backend:** ensure contract parity between canonical route and what the web needs; add explicit logging for `/stream` calls.
- **Phase 2 — frontend:** move UI to `POST /api/v2/estimate`; drop SSE parser dependency on the main v2 path; validate loading / error / success flows.
- **Phase 3 — observability:** ship with alias; review `/stream` logs/metrics for ~1–2 release cycles or **7–14 days** of real usage.
- **Phase 4 — cleanup:** remove `POST /api/v2/estimate/stream`, obsolete v2 SSE tests, stale docs, and helpers tied only to v2 stream.

## 6. Backend changes

**Router / controller**

- Keep `POST /api/v2/estimate` as the canonical route.
- During transition, mark `POST /api/v2/estimate/stream` deprecated; remove it in the final phase.
- If a temporary alias exists, avoid duplicated business logic: the deprecated handler delegates to the same service path as the canonical route.

**Service layer**

- Do not add a new abstraction if the service already returns `EstimationResponse`.
- Review `stream_structured_estimation` (or equivalent): keep only for temporary compatibility or delete when `/stream` is removed.
- Preserve guardrails, semantic cache, optional persistence, and structure evaluation on the canonical path.

**Pydantic models**

- Reuse `EstimationRequest` for input.
- Reuse `EstimationResponse` for output.
- Do not duplicate models for `/estimate` vs `/stream`.

**Validation**

- Keep existing form rules: lengths, enums, attachments, dates, lists, conditional fields.
- Ensure validation errors still return `422` with detail the frontend can parse.

**Logging**

- Log the canonical route with stable keys: `request_id`, `route`, `latency_ms`, `final_status`, `reason_code`, `cached`, `provider`, etc.
- For `/stream` during transition, log a dedicated event (e.g. `deprecated_estimate_stream_endpoint_used`) without full prompts or sensitive form data.

**Error handling**

- Keep user-safe error messages.
- Map blocking guardrail failures to `422`.
- Map provider/pipeline failures to `503` when there is no usable result.
- Never log or return API keys, full prompts, attachments, or sensitive user data.

**Tests to add or update**

- API test: `POST /api/v2/estimate` with minimal valid body and structured JSON response.
- API test: `422` for invalid payload.
- If alias remains: compatibility test for `/api/v2/estimate/stream` plus deprecation signal behavior.
- Final removal test: `/stream` is not a supported endpoint.
- Update tests that expect v2 SSE `done` events.

## 7. Frontend changes

**URL**

- Replace `POST /api/v2/estimate/stream` with `POST /api/v2/estimate`.
- Rename helpers to avoid `Stream` on the main v2 path (e.g. `estimateStructuredUrl`).

**Streaming coupling**

- Remove or isolate the SSE parser for v2 if unused elsewhere.
- Drop reliance on `done` / `chunk` / `error` events for the primary structured flow.
- Ensure UI copy no longer refers to “terminal `done` event” or SSE for v2.

**Client simplification**

- Replace `response.body.getReader()` loops with `const data = await response.json()`.
- Bind UI from `data.result` for cards, tables, and summary.
- Keep `AbortController` if the UI supports canceling long requests.

**State impact**

- **Loading:** starts on submit, ends on final JSON or error.
- **Error:** parse FastAPI JSON errors, especially `detail`.
- **Success:** `structuredResult = data.result`; retain metadata if displaying `usage`, `latency_ms`, or `cached`.
- **Cancel:** abort `fetch` and leave UI in a consistent non-partial state.

## 8. Observability and operations

**Logs**

- Log `/api/v2/estimate` calls with latency, final status, cache hit/miss, provider/model as applicable.
- During transition, log `/api/v2/estimate/stream` with deprecation metadata and operational counters.

**Metrics (examples)**

- Requests: `estimate_requests_total{route="/api/v2/estimate"}` and `estimate_requests_total{route="/api/v2/estimate/stream"}`.
- Latency: `estimate_request_latency_ms`.
- Errors: `estimate_errors_total{status_code="422|503|500"}`.
- Cache: `cached=true` ratio, `cache_miss_reason`, buckets without raw user text.

**Alerts**

- Elevated `5xx` on `/api/v2/estimate`.
- Weekly check: `/api/v2/estimate/stream` still receives traffic after migration window.
- p95 latency regression after frontend migration.

**Detecting remaining `/stream` consumers**

- Log queries: `route="/api/v2/estimate/stream"` or `deprecated_estimate_stream_endpoint_used`.
- Inspect `User-Agent`, origin, internal IP, or client id **without** storing sensitive payloads.
- Repo search: `estimate/stream`, `estimateStructuredStreamUrl`, `text/event-stream`, `chunk`, `done`.
- Gateway / proxy access logs if traffic is fronted.

## 9. Acceptance criteria

- `POST /api/v2/estimate` accepts the current web form payload and returns `application/json`.
- Successful responses include `result` matching the structured contract plus metadata compatible with `EstimationResponse`.
- Estimador CAG web submits the form to `/api/v2/estimate`.
- The web no longer depends on SSE for the primary v2 structured path.
- Loading, error, success, and cancel states work after migration.
- Validation errors remain legible in the UI.
- Repo-facing docs no longer describe `/api/v2/estimate/stream` as the main path or as real streaming.
- If a temporary alias exists, each `/stream` call is logged as deprecated usage.
- After the transition window, no material traffic to `/stream` before removal.
- Backend: `uv run pytest` passes for affected scope.
- Frontend: package test/build commands pass as configured.
- No new environment variables or secrets.

## 10. Risks and open decisions

**External or unknown consumers**

- Risk: scripts, demos, notebooks, internal clients, old deployments still call `/api/v2/estimate/stream`.
- Mitigation: temporary alias + deprecation logging + active code/docs/access-log search.

**Stale documentation**

- Risk: README, technical docs, and comments still claim v2 primary path is SSE.
- Mitigation: update in the same migration task; verify with text search.

**Internal helpers**

- Risk: names like `estimateStructuredStreamUrl` or `useEstimateStream` preserve wrong semantics even after URL change.
- Mitigation: rename in the frontend pass or isolate legacy-only names.

**Caches, proxies, gateways**

- Risk: special rules for `/stream` (`text/event-stream`, buffering, timeouts).
- Mitigation: review proxy config; ensure `/api/v2/estimate` has appropriate timeouts for non-streaming LLM requests.

**Open decision**

- Exact deprecation window length (suggest **7–14 days** or one full iteration after web migration, adjusted to release cadence and traffic visibility).

## 11. Implementation checklist

**Backend**

- [x] Confirm `POST /api/v2/estimate` covers the full contract required by the web.
- [x] Remove `POST /api/v2/estimate/stream` (Phase 4 cleanup in this work item).
- [ ] Temporary deprecated alias — **skipped** (this delivery removes the route outright).
- [ ] Per-request deprecation logging — **skipped** (not applicable once the route is gone).
- [x] Update API tests (including assertion that `/api/v2/estimate/stream` is not registered).

**Frontend**

- [x] Change URL from `POST /api/v2/estimate/stream` to `POST /api/v2/estimate`.
- [x] Headers: `Content-Type: application/json`, `Accept: application/json`.
- [x] Replace SSE parser with final JSON parse on the main v2 path.
- [x] Rename URL helper to `estimateStructuredUrl` (hook file name `useEstimateStream.ts` retained).
- [ ] Manual validation: loading, error, success, cancel in browser — **not run in this session** (covered by code paths + unit/API tests).

**QA**

- [ ] Happy path from web form (manual).
- [ ] Invalid payload shows a clear error (manual).
- [ ] Cancel works if supported (manual).
- [x] No SSE on the primary v2 path (web client uses JSON only).
- [x] Repo code has no v2 `/stream` URL in the workbench client.

**Documentation**

- [x] Root `README.md`
- [x] `docs/technical/README.md`
- [x] `web/README.md`
- [x] Stale v2 `/stream` references updated in repo-facing docs (`docs/architext/data/*` where applicable)
- [x] Removal milestone: route removed as part of this work item (no deprecation window in code).

**Note:** Sections 5–6 and line 369 above describe an optional phased rollout (alias + logs). **This work item implements the Phase 4 removal** named in the filename and section 5 Phase 4.

## Repository commits (master-ia)

| Commit  | Summary |
| ------- | ------- |
| `a05fb51` | `feat(api)`: remove `POST /api/v2/estimate/stream` |
| `d9011cb` | `feat(web)`: use JSON `POST /api/v2/estimate` for structured estimation |
| `c4de2f8` | `docs`: align product docs with v2 non-streaming estimate API |
| `46531d5` | `docs(work-items)`: record commits for feature-014 v2 stream removal |
| `5f19a7f` | `docs(cursor)`: default branch and remote PR in `start-task` |

**Git branch (policy note):** The commits above shipped on **`feature/remove-v2-estimate-stream`**. For any **new** work under this canonical file, `/start-task` requires **`feature/014-remove-v2-estimate-stream-route`** (see `.cursor/commands/start-task.md` Phase 4.1).
