# Feature: Supervisor/Worker Estimation with Conditional HITL (Session 14)

## Objective

Reorganize the existing Session 13 LangGraph estimation flow into an explicit
supervisor/worker multi-agent system inside the Python + FastAPI AI service.
This is the Session 14 exercise track; it evolves the graph shipped by
`feature-066` rather than adding a parallel one.

The new graph must preserve the existing estimation capabilities and public graph
API while moving runtime control-flow decisions into a hand-written supervisor.
Four least-privilege workers collaborate through one typed shared state:

- `requirements_extractor`
- `budget_searcher`
- `estimate_generator`
- `coherence_validator`

When validation identifies insufficient reliability, the graph must persist its
state through the existing `AsyncPostgresSaver`, pause with `interrupt()`, and
return `status="awaiting_human_review"`. A reviewer can then approve, adjust, or
reject the estimate through the existing resume capability.

The architectural goal is not to increase the node count. It is to make dynamic
routing, worker responsibility, tool privilege, accumulated evidence, and human
intervention explicit and observable.

## Context

### Existing baseline

`feature-066-langgraph-multi-agent-estimation-s13.md` delivered:

- `app/services/estimation_graph/state.py` with typed shared state and reducers.
- `app/services/estimation_graph/build.py` with a compiled `StateGraph`.
- `AsyncPostgresSaver` and pooled Postgres checkpoint lifecycle in
  `app/services/estimation_graph/checkpointer.py`.
- Human pauses with `interrupt()` and resumes with `Command(resume=...)`.
- `POST /api/v1/estimate/graph`,
  `POST /api/v1/estimate/graph/{estimation_id}/resume`, and state/progress
  endpoints.
- Existing structured extraction, historical retrieval, estimation, validation,
  logging, CLI, and test seams.

The current S13 topology is not a supervisor/workers topology. It uses a
classifier, structure agent, mandatory structure-review gate, per-task `Send`
fan-out, recovery join, analysis agent, and mandatory final-review gate. This
feature replaces that internal orchestration for the graph estimation path while
reusing the established infrastructure and business capabilities.

### Existing business tools

`app/services/agentic/agent_tools.py` already exposes the capabilities required by
this feature:

- `search_budgets(..., backend=...)`
- `calculate_estimate(...)`
- `validate_estimate(...)`

No new business tool is needed. Worker adapters may transform typed graph state
into existing tool arguments and map tool results back into partial state updates.

### Existing API compatibility

The canonical public surface remains `/api/v1/estimate/graph*`. The start route
continues to accept a transcript and an optional `estimation_id`; the resume route
continues to use that identifier as the LangGraph `thread_id`.

The required contract extension is:

- start may complete normally or return `status="awaiting_human_review"`;
- a paused response includes the review payload and identifiers needed to resume;
- resume accepts an explicit approve, adjust, or reject resolution.

Existing authentication, rate limits, request IDs, safe error mapping, state,
stream/progress, and proposal routes must not regress. The one deliberate
contract change is the meaning of `status` (see FR-10): S13's
`validated|needs_review` becomes `awaiting_human_review|completed|rejected`.

### Repository finding — edge-case transcript

Verified 2026-07-19: `sample_transcript_edge_case.txt` does not exist in
`master-ia`, and the official `ai-engineering` repo has no `session_14` branch
yet (latest is `session_13_live`), so there is no scaffold asset to port today.

Resolution:

- Before implementation, re-fetch the official repo; if a Session 14 branch has
  appeared, port its `sample_transcript_edge_case.txt` verbatim into
  `exercises/session-14/`.
- Otherwise, author the transcript in `exercises/session-14/` so that it
  **deterministically** triggers at least one review-policy condition (the most
  reliable is a domain with no historical precedent in the budget corpus, which
  fires the no-precedent signal regardless of model variance).
- The transcript must be at least 100 characters, because
  `GraphEstimateRequest.transcript` enforces `min_length=100`.
- Generated traces remain local artifacts and must not be committed.

### Affected Session 13 surfaces

Replacing the topology breaks more than `build.py`. These surfaces are coupled to
S13 node names or state fields and must be migrated or retired in this feature:

| Surface | Coupling | Required action |
| --- | --- | --- |
| `app/services/estimation_graph/agents/*` (classifier, structure, gates, hours, analysis) | S13 nodes | Retire modules and their tests; do not leave dead wired code. Reuse `complete_graph_structured` and `schemas.py` where useful. |
| `app/services/estimation_graph/activity.py` (`describe_node`) | S13 node names | Rewrite descriptions for supervisor/worker/human-review nodes. |
| `app/schemas/graph_estimation.py` (`GraphRunState.complexity/structure/task_hours/analysis_report`) | S13 state fields | Replace with the new state artifacts (`requirements`, `budget_matches`, `validation`, `confidence`); document the contract change. |
| `POST /graph/{id}/proposal` | Reads `estimate` + `analysis_report` from the snapshot | Keep working: `estimate` remains; feed `validation` where `analysis_report` was used, or accept an empty report. |
| `app/scripts/run_graph_s13.py` | `GATE_DECISIONS` keyed by S13 gate names; `render_run` renders S13 fields | Update gate name to `estimation_review`, decision shape to `{"action": ...}`, and the render to the new state. |
| `personas.py` | Persona keys per S13 agent | Re-key for the new workers or drop personas for retired nodes. |
| `tests/estimation_graph/`, `tests/routers/test_estimate_graph.py` | S13 topology and payloads | Rewrite alongside each step; they are the regression baseline. |

### Interpretation of “pure worker”

Workers use a pure graph-node contract: typed state in, partial state update out,
with no hidden mutable state. Model calls and business-tool calls are necessarily
I/O; they must be isolated behind injected or monkeypatchable dependencies. This
keeps state transformation explicit without falsely treating external calls as
mathematically pure.

## Scope

### Includes

- Replace the S13 graph topology with a hand-written supervisor and four workers.
- Retire the superseded S13 agent modules, activity descriptions, CLI gate
  decisions, and their tests (see "Affected Session 13 surfaces").
- Build the supervisor directly with `StateGraph` and `Command`; do not use
  `create_supervisor`.
- Make every supervisor transition observable as
  `Command(goto=..., update=...)`.
- Extend the existing typed state with transcript, requirements, historical
  matches, estimate, validation, confidence, execution status, routing metadata,
  human-review data, and accumulated worker contributions.
- Add at least one accumulator reducer; prefer keyed accumulation for historical
  matches and append-only agent contributions.
- Reuse `search_budgets`, `calculate_estimate`, and `validate_estimate`.
- Enforce least privilege by construction:
  - supervisor: no business tools;
  - requirements extractor: model only;
  - budget searcher: `search_budgets` only;
  - estimate generator: `calculate_estimate` only;
  - coherence validator: `validate_estimate` only.
- Add conditional HITL for low confidence, out-of-range estimates, or no relevant
  historical precedent.
- Reuse the existing `AsyncPostgresSaver` and checkpoint lifecycle.
- Support approve, adjust, and reject resume decisions with explicit Pydantic
  models.
- Preserve the existing graph API paths and additive stream/state/progress
  behavior.
- Add a deterministic network-free test suite using `MemorySaver`, mocked model
  calls, and fake retrieval.
- Add a manual or `slow` end-to-end trace using
  `sample_transcript_edge_case.txt`, including pause and successful resume.
- Update README, `.env.example`, technical architecture documentation,
  `docs/arquitectura-estimador-cag.html`, and the relevant learning note.

### Excludes

- New infrastructure, queues, databases, or messaging systems.
- New business tools beyond `search_budgets`, `calculate_estimate`, and
  `validate_estimate`.
- Replacing Postgres as the production checkpointer.
- Replacing existing RAG, CAG, Session 12 agent, session, or proposal APIs.
- A competing conservative/aggressive agent pattern.
- Deep sandboxing or provider-level tool isolation.
- A new frontend or reviewer UI.
- Broad HITL testing beyond the required deterministic graph/API paths and one
  complete edge-case trace.
- Migrating the repository to `structlog`; existing stdlib structured logging
  remains the default.
- Committing generated trace output.

## Functional Requirements

### FR-01 — Typed shared state

Extend `EstimationState` with fields equivalent to:

```text
transcript
estimation_id
requirements
budget_matches
estimate
validation
confidence
status
completed_workers
agent_contributions
human_review
human_resolution
errors
```

The exact internal types may reuse existing Pydantic and `TypedDict` models, but
the following invariants apply:

- all workers read and write the same shared state;
- each worker returns only its partial update;
- `status` is an explicit finite set, including at least `running`,
  `awaiting_human_review`, `completed`, and `rejected` (`running` is an internal
  in-flight value; the blocking API only surfaces the other three, while the
  progress-poll surface keeps its own `running|paused|completed` field);
- routing metadata prevents the supervisor from repeatedly selecting a worker
  that already attempted its responsibility without changing its prerequisites;
- accumulated data is resume-safe and does not silently duplicate entries.

At least one field must use an accumulator reducer. A keyed reducer for
`budget_matches` should use a stable identity such as
`(requirement_id, reference_budget_id)`; an append-only `agent_contributions`
channel may additionally record visible worker outputs.

### FR-02 — Hand-written supervisor

Implement `supervisor(state) -> Command` without business tools and without
`create_supervisor`.

The supervisor inspects state and returns `Command(goto=..., update=...)` for
every transition. Its routing policy must be explicit and deterministic:

1. Missing structured requirements → `requirements_extractor`.
2. Requirements present and historical search not attempted or incomplete →
   `budget_searcher`.
3. Search completed and no estimate → `estimate_generator`, including when no
   precedent was found so the risk can be validated rather than causing a loop.
4. Estimate present and not validated → `coherence_validator`.
5. Validation requires review and no human resolution exists →
   `human_review`.
6. Approved human resolution → `END` with `status="completed"`.
7. Adjusted resolution → route to `coherence_validator` exactly once for the
   folded adjustment (tracked with a bounded flag or counter), then finish with
   `status="completed"` — or, if revalidation still demands review, finish with
   the human's decision recorded rather than re-entering the review loop.
8. Rejected resolution → `END` with `status="rejected"`.
9. Valid estimate with no review signal → `END` with `status="completed"`.

Each decision updates routing metadata such as `last_route`, `route_reason`, or a
supervisor decision record so observability shows why the transition occurred.

### FR-03 — Requirements extractor

`requirements_extractor(state) -> partial update`:

- reads the transcript;
- uses the existing structured model boundary only;
- has no business-tool registry;
- emits validated structured requirements with stable identifiers or ordering;
- records an explicit contribution and completion marker;
- returns a safe error when extraction is empty or malformed.

### FR-04 — Budget searcher

`budget_searcher(state) -> partial update`:

- reads structured requirements;
- may invoke only `search_budgets`; the retrieval backend is injected using the
  existing seams (`build_retrieval_backend(...)` for production,
  `load_stub_retrieval_backend()` / fakes for offline runs and tests);
- performs focused searches per requirement or component;
- accumulates traceable matches in shared state;
- records that search was attempted even when no match exists;
- preserves reference identifiers, recorded hours, distance, and requirement
  association needed by estimation and validation.

The worker must not calculate or validate the estimate.

### FR-05 — Estimate generator

`estimate_generator(state) -> partial update`:

- reads requirements and accumulated historical matches;
- may invoke only `calculate_estimate`;
- maps matches to `reference_amounts` without inventing evidence;
- produces the structured estimate and contribution metadata;
- preserves unbudgeted components when no precedent exists.

The worker must not search for budgets or validate its own output.

### FR-06 — Coherence validator

`coherence_validator(state) -> partial update`:

- reads the estimate and its historical evidence;
- may invoke only `validate_estimate`;
- returns structured validation information;
- derives a normalized numeric confidence in the inclusive range `0.0..1.0`;
- exposes at least:
  - validation success/failure;
  - confidence;
  - out-of-historical-range signal;
  - no-precedent signal;
  - human-review reasons.

If the existing `validate_estimate` result does not directly contain all fields,
the worker may deterministically derive them from its result and the shared
evidence. This derivation is orchestration logic, not a new business tool.

### FR-07 — Conditional human-review policy

Human review is required when any of these conditions is true:

- `confidence < GRAPH_HUMAN_REVIEW_CONFIDENCE_THRESHOLD`;
- validation reports an estimate outside the historical range;
- at least one required component has no relevant historical precedent.

Add a typed setting:

```text
GRAPH_HUMAN_REVIEW_CONFIDENCE_THRESHOLD=0.70
```

The default may be adjusted during implementation only with documented evidence.
It must be validated in `0.0..1.0`, documented in `.env.example` and README, and
must not contain sensitive data.

### FR-08 — Persistent pause

The `human_review` node calls `interrupt()` with a payload containing at least:

```json
{
  "gate": "estimation_review",
  "estimation_id": "stable-thread-id",
  "status": "awaiting_human_review",
  "estimate": {},
  "validation": {},
  "confidence": 0.42,
  "review_reasons": []
}
```

The graph must be compiled with the existing checkpointer. In production, the
pause is persisted by `AsyncPostgresSaver`; tests use `MemorySaver`.

The interrupt node must avoid writing reducer-backed data before `interrupt()`,
because LangGraph re-executes the node on resume.

### FR-09 — Human resolution model

Expose a discriminated Pydantic resolution model with these variants:

- `approve`: accepts the proposed estimate.
- `adjust`: requires typed estimate adjustments or a complete adjusted estimate.
- `reject`: requires or permits a reviewer reason and finalizes as rejected.

Example payloads:

```json
{"action": "approve", "comment": "Historical analogy is acceptable."}
```

```json
{
  "action": "adjust",
  "adjusted_estimate": {
    "components": [],
    "total_hours": 420.0
  },
  "comment": "Adjusted integration effort after architecture review."
}
```

```json
{"action": "reject", "comment": "Transcript is insufficient; request a new discovery call."}
```

Unknown actions, invalid adjustments, and resume attempts without a pending
interrupt return safe 4xx responses and do not corrupt the checkpoint.

### FR-10 — Start API behavior

`POST /api/v1/estimate/graph` remains the canonical start operation. The request
keeps `transcript` (existing `min_length=100`, `max_length=50_000`) and optional
`estimation_id`.

`GraphRunState` today carries two related fields that this feature must
reconcile explicitly:

- `state`: run-lifecycle value (`paused` | `completed`) derived from the
  checkpointer snapshot — keep it;
- `status`: business status. S13 used `validated` | `needs_review`; this feature
  redefines it as `awaiting_human_review` | `completed` | `rejected`. The change
  is a deliberate breaking contract change for the business backend and must be
  documented in the technical note and API collection.

Normal completion returns HTTP 200 with:

```json
{
  "estimation_id": "...",
  "state": "completed",
  "status": "completed",
  "estimate": {},
  "validation": {},
  "confidence": 0.86
}
```

Conditional pause returns HTTP 200 with:

```json
{
  "estimation_id": "...",
  "state": "paused",
  "status": "awaiting_human_review",
  "pending_gate": {
    "gate": "estimation_review",
    "estimation_id": "...",
    "payload": {
      "estimate": {},
      "validation": {},
      "confidence": 0.42,
      "review_reasons": ["confidence below threshold"]
    }
  },
  "estimate": {}
}
```

The response must contain enough information for the business backend to present
the case and later resume the same checkpoint. Existing auth, rate limits, and
request-ID behavior remain unchanged.

### FR-11 — Resume API behavior

`POST /api/v1/estimate/graph/{estimation_id}/resume` remains the canonical resume
operation and accepts the typed human resolution.

- approve → complete with the accepted estimate;
- adjust → fold the adjustment into state, revalidate, and complete safely;
- reject → complete with `status="rejected"` and preserve review audit data;
- unknown run → 404;
- known run with no pending review → 409;
- invalid resolution → 422;
- graph unavailable → 503;
- internal graph/provider failure → safe 502.

### FR-12 — Least privilege

Tool access must be represented explicitly in code, not only in prompts.

Each worker receives or imports only its allowed capability. Tests must prove that:

- the supervisor has no dispatch path to a business tool;
- the extractor has an empty business-tool set;
- the budget searcher cannot call calculation or validation;
- the generator cannot call search or validation;
- the validator cannot call search or calculation.

Optional runtime action-policy validation may be added, but static construction
and deterministic tests are sufficient for the required scope.

### FR-13 — Observability

Existing tracing/logging must expose:

- supervisor route target and route reason;
- worker start/completion and contribution count;
- business tool name used by each worker;
- review trigger reasons;
- interrupt and resume action;
- final status.

Do not log full transcripts, secrets, API keys, or sensitive reviewer content.
Use stable stdlib logging keys and existing graph activity/tracing adapters.

### FR-14 — Edge-case deliverable

Add or port `sample_transcript_edge_case.txt`. A complete execution must:

1. start through the public API or CLI;
2. route through all four workers;
3. trigger at least one review condition;
4. pause with `status="awaiting_human_review"`;
5. persist a checkpoint under the same `estimation_id`;
6. resume with a valid human decision;
7. reach a final completed or rejected state;
8. show supervisor decisions, pause, and resume in the trace.

The trace output is a local deliverable and must not be committed.

### FR-15 — Additive safety

- Existing RAG, CAG, Session 12 agent, session, proposal, and health routes remain
  operational.
- Graph initialization failure must not prevent `/health` or unrelated routes
  from serving.
- Existing graph state, progress, stream, resume-stream, and proposal endpoints
  either remain compatible or receive an explicit adapter documented in the
  technical note.

## Technical Approach

### Target topology

```text
START
  → supervisor
      ├─Command→ requirements_extractor ─edge→ supervisor
      ├─Command→ budget_searcher        ─edge→ supervisor
      ├─Command→ estimate_generator     ─edge→ supervisor
      ├─Command→ coherence_validator    ─edge→ supervisor
      ├─Command→ human_review [interrupt] ─edge→ supervisor
      └─Command→ END
```

Static worker-to-supervisor return edges are acceptable. Every forward business
transition is selected by the supervisor through `Command(goto=..., update=...)`.

### Proposed file boundaries

```text
app/services/estimation_graph/
├── state.py
├── build.py
├── supervisor.py
├── review_policy.py
├── checkpointer.py                 # reuse, minimal/no change expected
└── agents/
    ├── requirements_extractor.py
    ├── budget_searcher.py
    ├── estimate_generator.py
    ├── coherence_validator.py
    └── human_review.py

app/schemas/graph_estimation.py
app/routers/estimate_graph.py
tests/estimation_graph/
tests/routers/test_estimate_graph.py
exercises/session-14/sample_transcript_edge_case.txt
```

Exact filenames may be consolidated when a smaller boundary is clearer, but the
supervisor, review policy, worker privileges, and API schemas must remain
independently testable.

### Worker dependency pattern

Prefer small typed factories or callables:

```python
budget_searcher = build_budget_searcher(search_budgets_fn)
estimate_generator = build_estimate_generator(calculate_estimate_fn)
coherence_validator = build_coherence_validator(validate_estimate_fn)
```

This gives each worker only its required capability and allows tests to inject
fakes without a global all-tools dispatcher. Reusing existing functions does not
require exposing the full `dispatch_tool` registry to every worker.

### Review flow

`human_review` is the only interrupt node. It receives the current risk payload,
calls `interrupt()`, validates the resumed value as `HumanResolution`, and returns
the partial update. The supervisor then decides:

- approve → final status;
- adjust → validator;
- reject → final rejected status.

Use an explicit state flag such as `human_adjustment_validated` or a bounded review
attempt counter to prevent accidental supervisor loops after adjustment.

### API migration

Keep `/api/v1/estimate/graph*` rather than introducing parallel endpoints. Adapt
`GraphResumeRequest` from an untyped `dict` to the discriminated resolution model.
If compatibility with legacy S13 gate decisions is still required, implement and
document a temporary adapter instead of accepting arbitrary dictionaries.

### Error handling

- Validate all model and tool outputs before adding them to state.
- Convert provider/tool failures at worker boundaries into domain-specific graph
  failures or explicit error contributions.
- Preserve the checkpoint for retryable failures.
- Return safe API errors without prompts, transcripts, stack traces, or secrets.

## Acceptance Criteria

- [ ] **AC-01:** `build_graph(...)` compiles the supervisor/workers topology
      without `create_supervisor`.
- [ ] **AC-02:** Every forward transition chosen by the supervisor returns
      `Command(goto=..., update=...)`, and tests assert route reasons for all
      worker, review, and terminal branches.
- [ ] **AC-03:** Shared typed state includes the required artifacts, execution
      status, human-resolution data, routing metadata, and at least one
      resume-safe accumulator reducer.
- [ ] **AC-04:** `requirements_extractor` uses the model boundary only and returns
      validated structured requirements as a partial update.
- [ ] **AC-05:** `budget_searcher` can invoke only `search_budgets` and accumulates
      traceable matches, including an explicit no-match outcome.
- [ ] **AC-06:** `estimate_generator` can invoke only `calculate_estimate` and
      preserves unbudgeted components without inventing references.
- [ ] **AC-07:** `coherence_validator` can invoke only `validate_estimate` and
      returns validation, numeric confidence, range/no-precedent signals, and
      review reasons.
- [ ] **AC-08:** The supervisor and extractor have no business-tool access;
      least-privilege tests fail if a worker is wired to an undeclared tool.
- [ ] **AC-09:** The graph completes normally without interruption when all
      review-policy conditions are false.
- [ ] **AC-10:** Any configured low-confidence, out-of-range, or no-precedent
      signal routes to `human_review` and returns
      `status="awaiting_human_review"`.
- [ ] **AC-11:** A paused run persists under the existing Postgres
      `AsyncPostgresSaver` thread/checkpoint identifier; the fast suite proves
      equivalent pause/resume semantics with `MemorySaver`.
- [ ] **AC-12:** Resume supports typed approve, adjust, and reject decisions;
      invalid decisions return 422, non-paused runs return 409, and unknown runs
      return 404.
- [ ] **AC-13:** Adjusted estimates are folded into shared state and revalidated
      without an infinite review loop.
- [ ] **AC-14:** `POST /api/v1/estimate/graph` preserves transcript input and
      normal estimate output while extending paused responses with review data.
- [ ] **AC-15:** State/progress/stream/resume-stream/proposal routes and unrelated
      estimation/health routes pass regression tests or have a documented
      compatibility adapter.
- [ ] **AC-16:** `GRAPH_HUMAN_REVIEW_CONFIDENCE_THRESHOLD` is typed, defaults to
      `0.70`, and is documented in `.env.example` and README.
- [ ] **AC-17:** Logs/traces show supervisor decisions, worker actions, review
      reasons, interrupt, resume action, and terminal status without sensitive
      payloads.
- [ ] **AC-18:** `sample_transcript_edge_case.txt` produces a complete trace that
      pauses and then resumes successfully; generated trace output is not
      committed.
- [ ] **AC-19:** Default automated tests require no real API keys, external LLM
      calls, or Postgres service.
- [ ] **AC-20:** README, technical docs, architecture HTML, canonical work item,
      and Session learning note describe the shipped topology and API behavior.

## Test Plan

### Unit tests

- `tests/estimation_graph/test_supervisor.py`
  - missing requirements;
  - search pending;
  - empty search completed;
  - estimation pending;
  - validation pending;
  - clean completion;
  - review routing;
  - approve/adjust/reject routing;
  - bounded adjustment path.
- `tests/estimation_graph/test_state.py`
  - keyed match reducer;
  - contribution accumulation;
  - idempotency across resume/re-entry.
- `tests/estimation_graph/test_review_policy.py`
  - threshold boundary;
  - out-of-range;
  - no precedent;
  - multiple reasons.
- `tests/estimation_graph/test_workers.py`
  - typed partial updates;
  - empty/malformed model output;
  - tool argument mapping;
  - no invented references;
  - confidence derivation;
  - least-privilege construction.
- `tests/test_config.py`
  - default and bounds for
    `GRAPH_HUMAN_REVIEW_CONFIDENCE_THRESHOLD`.

### Graph integration tests

- `MemorySaver` normal path: all workers → completed, no interrupt.
- `MemorySaver` risk path: all workers → interrupt → approve → completed.
- Adjust path: interrupt → adjusted estimate → validation → completed.
- Reject path: interrupt → rejected terminal state.
- Resume re-entry does not duplicate matches or contributions.
- Faked model and tool failures produce safe, traceable failures.

### API tests

- Start normal and paused responses.
- Resume approve/adjust/reject.
- 401 auth, 404 unknown run, 409 no pending review, 422 invalid resolution,
  502 graph failure, and 503 graph unavailable.
- State/progress/stream/resume-stream/proposal regressions.
- `/health` remains available when graph initialization fails.

### Manual and slow checks

```bash
uv run pytest tests/estimation_graph tests/routers/test_estimate_graph.py tests/test_config.py -q
uv run pytest -q
```

Manual deliverable (the CLI takes `--transcript` as a flag, not positional; its
`GATE_DECISIONS` and `render_run` must first be updated for the new
`estimation_review` gate and resolution shape — see "Affected Session 13
surfaces"):

```bash
uv run python app/scripts/run_graph_s13.py \
  --transcript exercises/session-14/sample_transcript_edge_case.txt \
  --out /tmp/supervisor_hitl_edge_case_trace.txt
```

The trace must show the pause (`awaiting_human_review`) and the auto- or
manually-supplied resolution that completes the run. A real Postgres checkpoint
smoke or real-model run must be marked/documented as `slow` and opted into
explicitly.

## Verification

### Automated

- Not run yet; this command creates the specification only.
- During implementation, run narrow RED/GREEN tests per baby step, then the
  feature-scoped suite and full default fast suite.

### Manual

- Not run yet.
- Required before closure: one edge-case execution that pauses, confirms the
  checkpoint/thread identifier, resumes with a human decision, and reaches a
  terminal state.

### Not verified yet

- Exact confidence calibration against production-like transcripts.
- Live Postgres pause duration across process restart.
- Live provider trace rendering.
- Compatibility needs for legacy S13 structure/final-review decision payloads.

## Documentation Plan

- `.env.example`: add `GRAPH_HUMAN_REVIEW_CONFIDENCE_THRESHOLD=0.70`.
- `README.md`: document supervisor/workers flow, conditional pause, response
  statuses, and resume examples.
- `docs/technical/estimation-graph-s13.md`: update or supersede with the new
  supervisor topology and migration notes.
- `docs/arquitectura-estimador-cag.html`: update graph topology, statuses,
  checkpoint flow, and resume contract.
- `exercises/session-14/README.md`: edge-case run and trace checklist.
- `learnings/docs/sesiones/`: add the relevant supervisor/HITL session note.
- API collection: update start and resume examples if that collection remains the
  repository's maintained manual contract.

## Implementation Plan

- [ ] **Step 1 — State and review policy:** extend typed state, add resume-safe
      reducers, typed resolution models, and confidence-threshold setting.
      **TDD:** reducer, policy, schema, and settings tests RED → GREEN.
- [ ] **Step 2 — Supervisor:** implement explicit `Command` routing and terminal
      decisions without business-tool access.
      **TDD:** supervisor route matrix RED → GREEN.
- [ ] **Step 3 — Requirements and budget workers:** add model-only extraction and
      search-only historical evidence accumulation.
      **TDD:** worker partial-update and privilege tests RED → GREEN.
- [ ] **Step 4 — Generation and validation workers:** adapt existing calculation
      and validation tools, derive confidence/review signals.
      **TDD:** mapping, unbudgeted, range, and confidence tests RED → GREEN.
- [ ] **Step 5 — Graph and conditional interrupt:** compile the new topology,
      implement `human_review`, retire the S13 agent modules and their wired
      edges (see "Affected Session 13 surfaces"), and prove
      normal/pause/approve/adjust/reject paths with `MemorySaver`.
      **TDD:** graph integration tests RED → GREEN.
- [ ] **Step 6 — HTTP contract:** adapt start/resume/state/progress schemas,
      rewrite `describe_node` activity descriptions, and preserve authentication,
      errors, stream, proposal, and health behavior.
      **TDD:** router contract and regression tests RED → GREEN.
- [ ] **Step 7 — Exercise and trace:** add the edge-case transcript, update the
      CLI (`--transcript` default, `GATE_DECISIONS`, `render_run`), and capture a
      local pause/resume trace.
      **TDD exception:** exercise asset and live trace are verified through CLI
      fixture tests plus a documented manual/slow smoke.
- [ ] **Step 8 — Documentation and closure:** update README, `.env.example`,
      technical docs, architecture HTML, learning note, verification evidence, and
      handoff.
      **TDD exception:** documentation-only; verify links, commands, and focused
      documentation checks where available.

## Estimation

- **Size:** L
- **Estimated time:** 2–3 focused days, excluding optional live-provider
  calibration.
- **Planned steps:** 8
- **Primary risks:** compatibility with legacy S13 gate payloads, confidence
  calibration, reducer idempotency on resume, and avoiding supervisor loops.

## Learnings and Pitfalls

- The existing S13 graph is already multi-agent, but not supervisor/workers.
  Preserve its infrastructure while replacing only the orchestration topology.
- A worker that calls a model or tool is not mathematically pure. Preserve the
  intended state-to-partial-update contract and isolate I/O behind explicit
  dependencies.
- “No matches” must be recorded as a completed search outcome; otherwise the
  supervisor can route forever between search and itself.
- Reducer-backed writes before `interrupt()` can duplicate data when LangGraph
  re-executes the node on resume.
- An adjusted estimate needs a bounded revalidation rule so it cannot create an
  endless HITL cycle.
- Tool privilege must be enforced by dependency construction, not only by prompt
  instructions.
- Confidence is a policy input, not an unexplained model opinion. Its derivation
  and threshold must be deterministic and testable where possible.
- `GraphRunState.state` (checkpoint lifecycle: `paused|completed`) and `status`
  (business outcome) are different fields; do not merge them, or the progress
  poll surface (`running|paused|completed`) breaks.
- S13 assets to reuse without change: `checkpointer.py`, `structured.py`
  (`complete_graph_structured`), auth/rate-limit middleware, and the router
  error-mapping pattern (401/404/409/502/503).
- feature-054 precedent: `OPENAI_TIMEOUT_SECONDS=30` is too short for live
  multi-turn runs; use a larger override (e.g. 600) for the manual edge-case
  deliverable.

## Implementation progress

- [x] Step 1: State and review policy
- [ ] Step 2: Supervisor
- [ ] Step 3: Requirements and budget workers
- [ ] Step 4: Generation and validation workers
- [ ] Step 5: Graph and conditional interrupt
- [ ] Step 6: HTTP contract
- [ ] Step 7: Exercise and trace
- [ ] Step 8: Documentation and closure

## Repository commits (master-ia)

| Commit | Summary |
| --- | --- |
| (pending) | Step 1: keyed budget-match reducer, review policy, typed HumanResolution, confidence threshold setting |

## Pull Request

- Draft WIP: https://github.com/povedica/master-ia-lidr/pull/61
- Branch: `feature/067-supervisor-worker-estimation-hitl`
- Label: `wip`

## How to start

```text
/start-task docs/work-items/feature-067-supervisor-worker-estimation-hitl.md
```
