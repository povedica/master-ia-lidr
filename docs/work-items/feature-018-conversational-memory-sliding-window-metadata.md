# Feature: Conversational Memory — Sliding Window + Distilled Project Metadata

## Objective

Evolve the estimator AI service from a transactional endpoint into a **multi-turn conversational estimator** with explicit separation between:

1. **Conversation history** — raw chronological messages, sliding window, system prompt always preserved.
2. **Project metadata** — distilled typed facts, stored separately, survive history truncation, injected into every system prompt, updated after each turn via an **LLM extractor**.

Wire feature-017 domain types into HTTP endpoints, prompt rendering, and a dedicated orchestration layer. **Do not** collapse history and metadata into one growing text blob.

## Context

### Already shipped (feature-017, merged)

`app/services/sessions.py` provides:

| Type | Role |
| --- | --- |
| `ChatMessage` | Frozen `role` + `content` |
| `ConversationHistory` | `max_turns` (default 10), `set_system_prompt`, `add_*`, `to_messages_list()` → `list[dict[str, str]]` |
| `ProjectMetadata` | `project_name`, `assumed_team_size`, `mentioned_technologies`, `agreed_scope` (all optional) |
| `Session` | `session_id`, `created_at`, `conversation_history`, `project_metadata` |
| `InMemorySessionStore` | `create_session`, `get_session`, `exists`, `delete_session` |
| `session_store` | Module singleton |

`tests/test_sessions.py` — 9 unit tests, all green on `main`.

### Current estimation stack (unchanged by feature-017)

- Routes: `app/routers/estimations.py` (`POST /api/v1/estimate`), `estimations_v2.py`.
- Service: `EstimationService` in `app/services/llm_service.py` — guided form, guardrails, cache, `render_estimation_prompt()`.
- Structured LLM: `complete_structured()` in `app/services/structured_llm_client.py` (Instructor + LiteLLM). Signature requires `litellm_model`, `chain_provider`, `api_key`, `timeout_seconds`, `system_prompt`, `user_prompt`, `max_output_tokens`, `response_model`, `max_attempts`. **There is no `acomplete_structured` helper.**
- Prompts: `app/services/estimation_prompt_rendering.py` + Jinja bundles under `app/prompts/estimation/`.

### Learnings from a premature implementation attempt (2026-05-18)

The following mistakes were made when code was written during `/write-feature` instead of `/start-task`. **Do not repeat:**

| Mistake | Impact | Correct approach |
| --- | --- | --- |
| Implemented code during `/write-feature` | Partial, untested feature; user expected spec only | **Only** edit `docs/work-items/` during `/write-feature`; run `/start-task` for code |
| Imported non-existent `acomplete_structured` | `ImportError` on `app.main` import; **3 test modules failed collection** | Use `complete_structured` with provider chain + settings (see `llm_service.py` ~748) |
| Registered `sessions` router before extractor worked | Entire API test suite blocked at import | Register router only after module imports cleanly; verify `uv run pytest --collect-only` |
| Stub assistant text in route handler | AC-05/07 not met; no real estimation | Thin router + `ConversationalEstimationService` calling `EstimationService` |
| `render_project_metadata_block` only in `sessions.py`, unused | AC-07 not met | Integrate via `estimation_prompt_rendering` or Jinja partial + tests |
| No `test_metadata_extractor.py` / `test_sessions_router.py` | AC-09–12 untested | TDD per `/start-task` hard stop |
| Merge logic without revision/removal | Doc promised removals; code only append/overwrite scalars | Define FR for merge; test explicit revisions |
| Renamed `conversation_history` → `history` without plan | Unnecessary churn vs feature-017 | Keep `conversation_history`; add `updated_at` only unless ADR says rename |

**Reverted state:** Only this work item exists on disk; no feature-018 application code remains on `main`.

### Evolution trigger — LLM call audit (feature-027, 2026-06-07)

Persisted call `output-responses/llm-call-20260607-111134-003.json` (turn 2 of a simplified session) exposed role-boundary defects:

| Role | Observed problem | Root cause |
| --- | --- | --- |
| **system** | Very long but structurally correct: identity, examples, output contract, `## Established project facts` | Metadata correctly injected via `render_session_system_prompt` |
| **user (history)** | `[Simplified submit] Corporate NGO Website` — label only, no turn intent | History stored synthetic labels instead of transcript snippets |
| **assistant (history)** | `Corporate NGO Website Development: A structured estimation for...` truncated mid-sentence | `_compact_estimation_summary` cut at 240 chars without word boundary |
| **user (current)** | Full guided form (~2k chars) duplicated project description already present in system metadata | Every turn re-rendered `guided_request.md.j2` regardless of `submit_count` |

**Impact:** redundant tokens, weak cross-turn signal in history, invalid assistant turns for the sliding-window contract enforced by `structured_llm_client._validate_messages_for_structured_completion`.

**Phase 2 (this update):** separate live LLM payload from stored history compaction; first turn = full guided form; subsequent turns = transcript delta only.

---

## Multi-turn message role design (canonical spec)

### 1. Executive summary

Multi-turn estimation already persists sessions, derived metadata, and a sliding window, but the provider payload mixed **persistent facts**, **raw history**, and **current intent** in the wrong roles. Turn 2+ re-sent the entire guided form in `user` while the same facts lived in `system`, and `assistant` history stored truncated synthetic summaries instead of valid prior model outputs. This evolution enforces a four-layer model—**system context**, **persistent memory**, **recent history**, **current user intent**—so each LLM call minimizes tokens, preserves facts across window trims, and keeps role alternation valid for structured completion. Value: lower cost, fewer contradictions, traceable audits via feature-027 JSON, and compatibility with existing `SimplifiedSessionEstimationService`, Jinja v2 templates, and `messages_override`.

### 2. Current problem

An approach that relies on resending raw history and full form payloads each turn causes:

- **Token growth:** project description + examples + metadata + full history on every call (3.2k+ prompt tokens on turn 2 in the audit sample).
- **Contradictions:** the model sees the same scope in system metadata and again in the current user block with slightly different wording.
- **Loss of useful context:** compact history labels (`[Simplified submit] …`) carry no revision signal; assistant history truncated mid-sentence is not usable recall.
- **Role ambiguity:** instructions and stable facts leak into `user`; synthetic strings stand in for `assistant` outputs.
- **Validation fragility:** `complete_structured` requires `system` first, alternating `user`/`assistant` pairs, and a final `user`—garbled assistant content breaks semantic continuity even when validation passes.

### 3. Design goals

| Principle | Rule |
| --- | --- |
| **System context** | Identity, estimation rules, examples, output contract, structured-output hints—stable per template version. |
| **Persistent memory** | Distilled `ProjectMetadata` / `DerivedProjectMetadata` injected only in `system` (`session_project_metadata.md.j2`). |
| **Recent history** | Last *N* user/assistant pairs—compact but semantically valid; no full form replay. |
| **Current intent** | `user` carries only this turn's delta (transcript, extras, new attachments). |
| **No duplication** | Facts in memory must not be re-expanded in current `user` on turn 2+. |
| **Revision path** | Explicit user language ("switch to Next.js", "drop Redis") updates memory via merge/extractor. |
| **Cost control** | Window cap (`max_turns`) + delta user messages + metadata block sized from populated fields only. |

### 4. Functional proposal — per-turn cycle

```text
a) load session          → InMemorySessionStore.get_session
b) build memory          → derive_project_metadata + merge_derived_metadata → ProjectMetadata
c) render system prompt  → render_estimation_prompt + render_session_system_prompt
d) build messages        → system + history_window + current_user_delta
e) call model            → LLMPipeline.run_structured(messages_override=…)
f) update history        → add compact user transcript + complete assistant summary
g) update memory         → project_metadata / last_derived_metadata on session
```

**Turn index behaviour:**

- **Turn 1 (`submit_count == 0`):** current `user` = full `guided_request.md.j2` (+ attachment block on first turn).
- **Turn 2+:** current `user` = `session_turn_delta.md.j2` (transcript + optional extras/attachments + output prefs reminder).

### 5. Prompt role design

| Role | Must contain | Must not contain | Example (allowed) | Example (forbidden) |
| --- | --- | --- | --- | --- |
| **system** | Persona, rules, examples, output contract, established facts | Current turn transcript; raw chat log | `## Established project facts … Agreed scope: WordPress NGO site` | `Add Redis this turn` |
| **user (current)** | Turn delta, explicit revisions, attachment deltas | Repeated full project description when memory exists | `## Turn update\nAdd Redis for session tokens.` | Re-posting entire `project_description` on turn 2+ |
| **assistant (history)** | Prior estimate acknowledgement with title, summary fragment, totals | Mid-sentence truncation; JSON blobs | `Estimate «Portal»: B2B SaaS scope… Totals: 120h.` | `Corporate NGO Website Development: A structured estimation for the dev…` |
| **user (history)** | Compact transcript snippet with turn index | Full guided form | `[Turn 2] Add Redis caching for session tokens.` | `[Simplified submit] Acme` only |

**Anti-mixing rule:** if a fact is in `ProjectMetadata`, the current `user` message must reference it only when the user **changes** it this turn.

### 6. Proposed data model

| Field | Type | Purpose | Example | Persistent / derived |
| --- | --- | --- | --- | --- |
| `Session.session_id` | `str` | Identity | `b90b4079-…` | Persistent (in-memory) |
| `Session.conversation_history` | `ConversationHistory` | Sliding window | system + 3 pairs | Persistent |
| `Session.project_metadata` | `ProjectMetadata` | LLM-facing distilled facts | `agreed_scope: "WordPress NGO site"` | Persistent, derived |
| `Session.last_derived_metadata` | `DerivedProjectMetadata` | UI + merge source | `detected_constraints: ["WordPress"]` | Persistent, derived |
| `Session.submit_count` | `int` | Turn index for delta vs full | `2` | Persistent |
| `ChatMessage.role` | `system\|user\|assistant` | Provider role | `user` | Derived per turn |
| `ChatMessage.content` | `str` | Payload | `[Turn 1] We need…` | Derived |
| `ProjectMetadata.agreed_scope` | `str?` | Scope summary | NGO WordPress site | Derived, in system |
| `ProjectMetadata.explicit_constraints` | `list[str]` | Hard constraints | `["WordPress CMS"]` | Derived, in system |

`ConversationSession` maps to `Session`; `Message` maps to `ChatMessage`; `ProjectMemory` maps to `ProjectMetadata` + `DerivedProjectMetadata`.

### 7. Memory update strategy

**Hybrid (recommended):**

1. **Deterministic derive (primary for simplified flow):** `derive_project_metadata` from explicit fields + transcript + attachments on each submit; `merge_derived_metadata` across turns.
2. **LLM extractor (conversational free-text path):** `metadata_extractor.extract_and_merge_metadata` after each turn in `ConversationalEstimationService`.

**Promotion history → memory:** when a fact appears in ≥1 turn and is not superseded, merge into metadata; do not rely on history retention.

**Revision detection:** explicit phrases ("instead", "no longer", "switch to", "remove", "olvida") trigger overwrite/remove in merge rules.

**Conflict policy:** latest explicit user revision wins; `rejected_options` removes stale list items; scalars clear on explicit null from extractor.

### 8. Technical changes on existing architecture

| Component | Change type | Work |
| --- | --- | --- |
| `estimation_prompt_rendering.py` | **Extension** | `render_session_turn_user_message` |
| `session_turn_delta.md.j2` | **New** | Delta template for turn 2+ |
| `simplified_session_estimation_service.py` | **Refactor** | Delta user payload; history compaction helpers |
| `sessions.py` | Unchanged | `ConversationHistory` window logic reused |
| `structured_llm_client.py` | Unchanged | Role validation already correct |
| `llm_call_audit` / feature-027 | Observability | Audit JSON confirms role shapes |
| `conversational_estimation_service.py` | Follow-up | Align free-text path with same role rules |
| Tests | **Extension** | Prompt + history + integration assertions |

### 9. Per-turn orchestration algorithm

```text
function run_submit(session_id, request):
    session = store.get(session_id)
    request = apply_field_defaults(session, request)
    derived = derive_metadata(request, attachments)
    merged = merge_derived(session.last_derived_metadata, derived)
    guided = adapt_to_estimation_request(request, …)
    is_first = (session.submit_count == 0)

    system = render_session_system_prompt(
        render_estimation_prompt(guided).system_prompt,
        to_project_metadata(merged),
    )
    session.conversation_history.set_system_prompt(system)

    current_user = render_session_turn_user_message(request, guided, is_first_turn=is_first)
    messages = session.conversation_history.to_messages_list() + [{role: user, content: current_user}]

    outcome = pipeline.run_structured(…, messages_override=messages)

    if outcome.success:
        session.conversation_history.add_user_message(user_history(request, turn_index=session.submit_count+1))
        session.conversation_history.add_assistant_message(assistant_history(outcome.result))
        session.project_metadata = to_project_metadata(merged)
        session.submit_count += 1
    return outcome
```

### 10. End-to-end examples

**Example A — Turn 1 (initial scope)**

- **User message (API):** transcript describing WordPress NGO site.
- **System (summary):** estimator persona + examples + `Established project facts: project_name, agreed_scope`.
- **History window:** `[]` (no prior turns).
- **Current user:** full guided form with product context + description.
- **Assistant:** structured `EstimationResult` (not duplicated in spec).
- **Memory after:** `project_name`, `agreed_scope`, constraints populated.

**Example B — Turn 2 (additive)**

- **User message:** `Same project — add Redis caching for sessions.`
- **System:** same base + updated metadata including prior scope.
- **History:** `[Turn 1] We need…` / `Estimate «NGO Site»: … Totals: 176h.`
- **Current user:** `## Turn update\nAdd Redis caching…` (no full description).
- **Memory after:** `explicit_constraints` includes Redis.

**Example C — Turn 3 (explicit revision)**

- **User message:** `Switch stack from WordPress to Next.js static site.`
- **Current user:** delta with revision language only.
- **Memory after:** `rejected_options` includes WordPress; scope updated; history still compact.

### 11. Risks and edge cases

| Case | Mitigation |
| --- | --- |
| Ambiguous input | Keep transcript verbatim in current `user`; warnings in response |
| Contradictions | Revision keywords + merge rules; metadata timestamp via `updated_at` |
| Stale memory | User delta explicitly revises; extractor path for free-text sessions |
| Too much metadata | Render only populated fields; cap list lengths in merge |
| Hallucinated facts | Never promote assistant output to memory without merge/extractor validation |
| Partial session reset | `submit_count` + `last_derived_metadata` gate first-turn vs delta |

### 12. Phased implementation plan

| Phase | Scope | Impact | Risk | Acceptance |
| --- | --- | --- | --- | --- |
| **P1 (done 2026-05)** | Session store, metadata block, extractor, router | Baseline multi-turn | Extra LLM call | AC-01–14 original |
| **P2 (2026-06)** | Delta user template, history compaction, audit validation | Token reduction, valid roles | Integration test updates | Turn 2+ user excludes full description; assistant history complete |
| **P3 (follow-up)** | Align `ConversationalEstimationService` + wire extractor on simplified path | Single memory policy | Dual code paths | Same role rules in both entry points |
| **P4 (follow-up)** | Optional LLM memory extractor for simplified submits | Better implicit revisions | Cost | Revision integration tests |

### 13. Acceptance criteria (phase 2)

- [x] AC-15: Turn 1 current `user` includes full guided form context.
- [x] AC-16: Turn 2+ current `user` uses `session_turn_delta.md.j2` and excludes `project_description` body.
- [x] AC-17: History user messages use `[Turn N] {transcript snippet}` not `[Simplified submit]`.
- [x] AC-18: History assistant messages start with `Estimate «{title}»:` and end with complete `Totals: {hours}h.` when space allows.
- [x] AC-19: `messages_override` still satisfies `structured_llm_client` role alternation.
- [ ] AC-20: `ConversationalEstimationService` free-text path aligned (deferred P3).

### 14. Testing strategy

- **Unit:** `render_session_turn_user_message` first vs subsequent; `_user_history_message`; `_assistant_history_message`.
- **Integration:** `test_two_linked_submits` asserts turn-2 `user_prompt` excludes turn-1 transcript body; sliding-window test unchanged.
- **Contract:** feature-027 JSON review—`model_request.messages` roles and content shapes.
- **Regression:** `uv run pytest tests/test_estimation_prompt_rendering.py tests/test_simplified_session_messages.py tests/test_sessions_integration.py`.

### 15. Development deliverables

- [x] Work item update (this section)
- [x] `session_turn_delta.md.j2`
- [x] `render_session_turn_user_message`
- [x] `simplified_session_estimation_service` history helpers
- [x] Unit + integration tests
- [ ] README note on turn delta behaviour (optional one-liner)
- [ ] P3: conversational service alignment

---

## Scope

### Includes

- Extend `ProjectMetadata`: `explicit_constraints`, `rejected_options`.
- Extend `Session`: `updated_at` (UTC), touched on each estimate turn.
- `POST /api/v1/sessions` — create session, return `session_id`.
- `POST /api/v1/sessions/{session_id}/estimate` — conversational turn (see FR-02 for payload).
- `app/services/metadata_extractor.py` — LLM extractor + validated merge into `ProjectMetadata`.
- `app/services/conversational_estimation_service.py` (or equivalent) — orchestration: load session, compose prompts with metadata + history, call estimation, append turns, run extractor, persist in store.
- `app/routers/sessions.py` — thin HTTP layer only.
- Prompt integration: inject populated metadata into system prompt every turn (no `"None"` placeholders).
- Tests: domain extensions, extractor (mocked LLM), router integration (TestClient).
- README / root endpoint: document new routes.
- Architecture note in this document (LLM extractor vs heuristics) — keep § Architecture Decision below.

### Excludes

- Attachment handling in session context.
- Persistence (database, Redis, filesystem).
- Background TTL cleanup jobs (optional one-line TODO on store only if obvious).
- Unrelated refactors (guardrails, semantic cache, observability).
- Changing non-session `/api/v1/estimate` or `/api/v2/estimate` contracts unless required for shared prompt helpers.

## Functional Requirements

### FR-01: Session creation

- `POST /api/v1/sessions` returns **201 Created** with body `{ "session_id": "<uuid>" }`.
- Store initializes empty `ConversationHistory` and empty `ProjectMetadata`.
- Two consecutive creates return **different** UUIDs.

### FR-02: Conversational estimate turn

**Request (decision for implementer):** Prefer a dedicated schema, e.g. `SessionEstimateRequest`, containing:

- `user_message: str` (required) — free-text turn for the conversational path.
- Optional: reuse fields from `EstimationRequest` only if product needs guided-form fields in-session (default: **free-text only** for v1 of this feature to limit scope).

**Flow:**

1. Load session by `session_id`; **404** if missing.
2. Build system prompt = base estimation system + **metadata block** (populated fields only) + instruction to treat metadata as established facts unless the current turn revises them.
3. Ensure `conversation_history` has system prompt set (first turn or when template version changes — document rule in code).
4. Append user message to history **before** LLM call (or per product rule, but be consistent and tested).
5. Call existing estimation pipeline with messages = `history.to_messages_list()` + current user message (avoid duplicating user line).
6. Append assistant message (serialized estimation summary or structured response text — match existing API patterns).
7. Run metadata extractor (FR-03).
8. Update `session.updated_at`.
9. Return same response shape as existing estimate endpoints where practical (`EstimateResponse` / structured v2 — pick one and document in OpenAPI).

**Must not** return hardcoded placeholder assistant text.

### FR-03: LLM metadata extractor

**Inputs:** current `ProjectMetadata`, latest user turn, latest assistant turn.

**Mechanism:**

- Call `complete_structured()` with a narrow system prompt and `response_model=ProjectMetadata` (or a dedicated `ProjectMetadataUpdate` model if partial updates are clearer).
- Use provider chain + settings (same as estimation), not a fictional wrapper.

**Merge rules (post-validation):**

| Field kind | Rule |
| --- | --- |
| Scalars (`project_name`, `assumed_team_size`, `agreed_scope`) | Overwrite when extractor returns non-`None`; support **clear** when extractor returns `null` and user explicitly revoked fact (test with example) |
| Lists (`mentioned_technologies`, `explicit_constraints`, `rejected_options`) | Append new items case-insensitively without duplication; support **removal** when user clearly rejects a prior item (test with example) |

**On failure:** Raise or map to a **controlled HTTP error** (e.g. 503 with safe message) after retries — do not silently leave metadata unchanged unless product explicitly chooses fallback (if fallback, document in AC and test).

### FR-04: Prompt rendering

- Add a single tested entry point, e.g. `render_session_system_prompt(base_system: str, metadata: ProjectMetadata) -> str` in `estimation_prompt_rendering.py` or a Jinja partial fed by `build_prompt_render_context`.
- Include only populated metadata fields.
- Never emit `project_name: None` or similar placeholders.

### FR-05: History sliding window

- Reuse feature-017 `ConversationHistory` behavior: system prompt always first; drop oldest user/assistant **pairs** when `len(_turns) // 2 > max_turns`.
- `project_metadata` on the session **must not** be trimmed when history is trimmed (test AC-08).

### FR-06: Store encapsulation

- All session access via `InMemorySessionStore` methods; no raw `_sessions` dict access outside `sessions.py`.
- Optional `save(session)` only if mutation patterns require it; in-place mutation of stored `Session` is acceptable if documented.

## Technical Approach

```text
Client
  → POST /api/v1/sessions
  → POST /api/v1/sessions/{id}/estimate
       → routers/sessions.py (HTTP only)
       → conversational_estimation_service.py
            → sessions.session_store
            → estimation_prompt_rendering (metadata + system)
            → EstimationService / llm_service (existing)
            → metadata_extractor → complete_structured
       → response
```

**Files to create or modify (planned):**

| File | Action |
| --- | --- |
| `app/services/sessions.py` | Extend metadata + `updated_at` |
| `app/services/metadata_extractor.py` | New |
| `app/services/conversational_estimation_service.py` | New orchestrator |
| `app/routers/sessions.py` | New |
| `app/schemas/session_estimation.py` (or similar) | New request/response models |
| `app/services/estimation_prompt_rendering.py` | Metadata injection |
| `app/main.py` | Register router **after** imports verified |
| `tests/test_sessions.py` | Extend |
| `tests/test_metadata_extractor.py` | New |
| `tests/test_sessions_router.py` | New |
| `README.md` | New endpoints |

**Provider call pattern for extractor (reference):**

```python
# Pattern from llm_service.py — adapt with settings + build_provider_chain()
domain_result, raw_usage, finish = await complete_structured(
    litellm_model=litellm_model,
    chain_provider=provider.name,
    api_key=api_key,
    timeout_seconds=timeout,
    system_prompt=extraction_system,
    user_prompt=extraction_user,
    max_output_tokens=...,
    response_model=ProjectMetadata,
    max_attempts=settings.structured_output_max_attempts,
)
```

**Environment variables:** Reuse existing OpenAI/LiteLLM settings; no new secrets. If a cheaper model is desired for extraction, add optional `OPENAI_METADATA_MODEL` in a follow-up (out of scope unless needed).

## Acceptance Criteria

- [x] AC-01: `POST /api/v1/sessions` returns 201 with valid UUID `session_id` and empty history/metadata.
- [x] AC-02: Two session creates return distinct IDs.
- [x] AC-03: `ConversationHistory` keeps system prompt first after any number of trims.
- [x] AC-04: When `max_turns` exceeded, oldest user/assistant pair is removed; newer pairs remain.
- [x] AC-05: `POST /api/v1/sessions/{id}/estimate` returns success for valid session using **real** estimation path (mocked LLM in tests).
- [x] AC-06: After estimate, session history contains new user and assistant messages.
- [x] AC-07: Metadata block appears in composed system prompt (assert via mock/spy on render function).
- [x] AC-08: After forced history trim, `project_metadata` fields set earlier remain on session.
- [x] AC-09: Extractor validates LLM output with Pydantic; invalid output handled per FR-03 (tested).
- [x] AC-10: No-op turn preserves prior metadata scalars and lists.
- [x] AC-11: New list items append without duplication.
- [x] AC-12: Explicit user revision/removal updates or clears stale facts (tested).
- [x] AC-13: `uv run pytest` full suite passes; `uv run pytest --collect-only` has zero errors.
- [x] AC-14: No secrets in code, tests, or docs.

## Test Plan

### Unit

- `tests/test_sessions.py` — new metadata fields, `updated_at`, render helper if kept at domain layer.
- `tests/test_metadata_extractor.py` — merge preserve/append/revise/remove; mock `complete_structured`.

### Integration

- `tests/test_sessions_router.py` — TestClient: create session, estimate, 404 unknown session, history growth, metadata injection spy.

### Regression

- `uv run pytest` (full suite) after registering router in `main.py`.

### Manual

```bash
uv run uvicorn app.main:app --reload
curl -s -X POST http://localhost:8000/api/v1/sessions | jq
curl -s -X POST http://localhost:8000/api/v1/sessions/<id>/estimate \
  -H 'Content-Type: application/json' \
  -d '{"user_message": "Estimate a Python FastAPI CRUD, team of 3"}' | jq
```

## Verification

- **Automated:** `uv run pytest tests/test_sessions.py tests/test_metadata_extractor.py tests/test_sessions_router.py -v` — **Verified** (2026-05-18).
- **Automated (regression):** `uv run pytest` — **Verified** (265 passed, 2026-05-18).
- **Import gate:** `uv run python -c "from app.main import app"` — **Verified** (2026-05-18).
- **Manual:** curl flow above — **Not verified** (requires live server + API key).
- **Not verified:** multi-worker memory, persistence migration, production cost of extra LLM call per turn

## Documentation Plan

- `README.md`: document `/api/v1/sessions` and `/api/v1/sessions/{id}/estimate`.
- `app/main.py` `read_root()` keys for discoverability.
- Docstrings on store (volatility) and extractor (LLM strategy).
- This work item: update `## Implementation progress` and `## Repository commits` during `/start-task` / `/finish-task`.

## Implementation Plan

Recommended baby steps for `/start-task` (TDD each logic step):

- [ ] Step 1: Extend `ProjectMetadata` + `Session.updated_at` + tests (RED → GREEN).
- [ ] Step 2: `render_session_system_prompt` / Jinja integration + tests (metadata injection, no None placeholders).
- [ ] Step 3: `metadata_extractor` with `complete_structured` mock + merge tests (preserve/append/revise/remove).
- [ ] Step 4: `conversational_estimation_service` orchestration + unit tests (mock estimation + extractor).
- [ ] Step 5: `routers/sessions.py` + `test_sessions_router.py`; verify `--collect-only` clean.
- [ ] Step 6: Register router in `main.py`, README, full `pytest`, sync AC checkboxes.

## Estimation

- Size: M
- Estimated time: 3–4 hours
- Planned steps: 6

## Implementation progress

- [x] Step 1: Extend `ProjectMetadata` + `Session.updated_at` + tests (RED → GREEN)
- [x] Step 2: `render_session_system_prompt` + tests (metadata injection, no None placeholders)
- [x] Step 3: `metadata_extractor` with `complete_structured` mock + merge tests
- [x] Step 4: `conversational_estimation_service` orchestration + unit tests
- [x] Step 5: `routers/sessions.py` + `test_sessions_router.py`; `--collect-only` clean
- [x] Step 6: Register router in `main.py`, README, full `pytest`, sync AC checkboxes
- [x] Step 7 (phase 2): Delta user template + history role compaction + tests (2026-06-07)

## Pull Request

- https://github.com/povedica/master-ia-lidr/pull/15 — merged via `/finish-task` (2026-05-18).

## Architecture Decision — Why LLM Extractor Over Heuristic Extraction

> **Canonical rationale for the extractor choice.** Implementation learnings and v1 trade-offs are in **Learnings** below.

**1. Why history and project_metadata must be separate**

History is raw, append-only, and lossy (sliding window). Metadata is distilled, slowly growing, and queryable. One blob would make prompts grow O(n) with conversation length and lose facts when old turns are dropped.

**2. Why sliding window is enough for history**

Estimation sessions rarely need more than the last ~10 turns once scope stabilizes. `max_turns=10` bounds tokens and cost. Deeper recall can be added later (summary layer, RAG) without changing the `Session` aggregate.

**3. Why metadata surviving truncation helps**

- **Coherence:** model always sees agreed facts.
- **Cost:** small structured block vs full transcript.
- **Auditability:** log metadata snapshot per turn.

**4. Why LLM extractor vs heuristics (decision summary)**

| Approach | Limitation in this product |
| --- | --- |
| Regex / keyword heuristics | Break on free-form, bilingual, and implicit revisions ("ya no usamos React", "team 4–5", "olvida lo del MVP"). |
| Rule-based NER on turns | High maintenance; every new field needs new patterns; removals/revisions are ambiguous. |
| **LLM extractor + Pydantic + merge tests** | Maps intent to typed `ProjectMetadata`; `complete_structured` reuses the existing provider chain; merge rules are deterministic and testable. |

We rejected heuristics because estimation input is conversational and unstructured. The extractor is a **narrow second call** (small schema, low temperature) whose output is never trusted blindly — it passes through Pydantic and explicit merge logic (`merge_project_metadata`).

**5. Trade-offs accepted**

- +1 LLM call per turn (cost, ~300–800 ms latency).
- Hallucination / missed revision risk → mitigated by Pydantic validation, explicit merge tests (preserve / append / clear / remove), and a narrow extraction prompt.

**6. Why in-memory is acceptable now**

Domain types are persistence-agnostic. Swapping `InMemorySessionStore` for Redis/Postgres should not change routers, extractor, or prompt code.

## Learnings

### Process

- `/write-feature` must **never** ship application code; ambiguous prompts that say "implement" still mean **spec only** unless the user runs `/start-task` on the work item path.
- Verify `complete_structured` exists before any import from `structured_llm_client`.
- Run `uv run pytest --collect-only` before merging router registration.
- Avoid route-level stubs; orchestration service + existing `EstimationService` keeps boundaries clean.

### Technical (feature-018 implementation)

- **LLM extractor choice held in production:** see **Architecture Decision §4** — heuristics were rejected for bilingual/free-form revision language; the extractor reuses `complete_structured` + `ProjectMetadata` with deterministic merge (`model_fields_set` for partial patches, case-insensitive list dedupe, `rejected_options` driving technology removal).
- **`system_prompt_override` on `EstimationService.estimate()`** was the smallest hook to inject metadata-enriched system prompts without forking the provider chain.
- **Multi-message provider wiring (2026-05+):** `SimplifiedSessionEstimationService` passes `messages_override = history.to_messages_list() + current_user` into `complete_structured`. Phase 2 (2026-06) fixed **what** goes into each role; sliding window + metadata separation remain as designed.
- **`_prepare_call` runs twice per turn** today (orchestrator + `estimate()`); acceptable for v1 but worth deduplicating if latency becomes visible.
- **Failed estimate after `add_user_message`** can orphan a user line in history; **failed metadata extraction after a successful estimate** returns 503 while the session already has the assistant turn — document as residual risk; consider best-effort metadata or transactional turn boundaries in a follow-up.

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `eff5b99` | `docs(feature-018): add conversational memory work item and start-task plan` | Canonical work item + estimation/plan. |
| `c317278` | `feat(feature-018): extend ProjectMetadata and Session.updated_at` | Domain fields + unit tests. |
| `4480541` | `feat(feature-018): add render_session_system_prompt for metadata injection` | Jinja partial + prompt rendering tests. |
| `8b618c8` | `feat(feature-018): add metadata extractor with merge rules` | LLM extraction + merge unit tests. |
| `25b7ba4` | `feat(feature-018): add conversational estimation orchestration service` | Turn orchestration + service tests. |
| `d457ca2` | `feat(feature-018): add sessions router and integration tests` | HTTP routes without main registration. |
| `2b64631` | `feat(feature-018): register sessions routes and document API` | main.py, README, AC-08 test, full regression. |
| `f39ac51` | `docs(feature-018): expand learnings and LLM extractor architecture rationale` | Architecture decision table + implementation retrospective. |
| *(pending)* | `feat(feature-018): delta user turns and valid assistant history roles` | Phase 2 role separation from audit JSON. |

### Verification (phase 2, 2026-06-07)

- **Verified:** `uv run pytest tests/test_estimation_prompt_rendering.py tests/test_simplified_session_messages.py tests/test_sessions_integration.py` → 11 passed, 9 skipped.
- **Verified (regression):** `uv run pytest` → 288 passed, 9 skipped (2026-06-07).
- **Not verified:** live re-run with `LLM_CALL_PERSIST_ENABLED=true` to confirm JSON shape on turn 2+.
- **Residual risk:** `ConversationalEstimationService` free-text path still uses full user message each turn (AC-20 deferred); `estimate_structured` still re-renders prompts and overwrites audit `variables_before_render` examples vs `system_prompt_override` content.
