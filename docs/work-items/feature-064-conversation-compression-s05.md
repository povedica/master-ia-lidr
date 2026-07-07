# Feature: Conversation Compression S05 (Phase 4 parity)

## Objective

Port official **Session 05 hybrid memory compression** into `master-ia` session estimation:

1. `AnchorDetector` — flag durable user commitments (heuristic mode default; optional LLM mode behind flag).
2. `CumulativeSummarizer` — fold older non-anchor turns into a running summary via structured LLM.
3. `CompressionPolicy` — orchestrate when to anchor vs summarize vs drop from the sliding window.

Integrate into `ConversationHistory` / session estimate path so long sessions (≥15 turns) retain anchor facts.

This is **Phase 4 parity** child slice of `docs/work-items/feature-053-official-master-parity-alignment.md` (FR-21).

## Context

### Official reference

| Artifact | Official path | Behavior |
| --- | --- | --- |
| Anchors | `conversation/compression/anchors.py` | Heuristic + optional LLM anchor detection |
| Summarizer | `conversation/compression/summarizer.py` | Cumulative summary envelope |
| Policy | `conversation/compression/policy.py` | Per-turn compression decisions |
| Models | `conversation/models.py` | `anchors` list on compressed history |

### `master-ia` fork choices

- New package `app/services/conversation_compression/` (not `embedding_pipeline`).
- Summarizer uses `complete_structured` or text completion via existing provider chain (not `LLMWrapper`).
- Default **heuristic anchors only**; `ANCHOR_DETECTOR_MODE=llm` opt-in.
- Integrate at `ConversationHistory` boundary used by `app/routers/sessions.py` estimate flow.
- Preserve existing `max_turns` sliding window as fallback when compression disabled.
- Stdlib logging; settings-driven models.

### Parent roadmap

- Depends on: none (can run parallel to Phase 2/3).
- Does not block RAG parity track.
- Optional eval: session golden YAML in `tests/evals/`.

## Scope

### Includes

- `anchor_detector.py`: `AnchorDetector`, `AnchorMatch`, heuristic rules port.
- `summarizer.py`: `CumulativeSummarizer` with mocked LLM tests.
- `policy.py`: `CompressionPolicy.apply_turn()` / `compress_history()`.
- Extend `ConversationHistory` or wrapper `CompressedConversationHistory` exposing `to_messages_list()` for estimation.
- Wire into session estimate path when `CONVERSATION_COMPRESSION_ENABLED=true`.
- Settings: `CONVERSATION_COMPRESSION_ENABLED`, `ANCHOR_DETECTOR_MODE`, `COMPRESSION_MODEL`, `COMPRESSION_MAX_SUMMARY_TOKENS`.
- Unit tests from official patterns (`test_compression_anchors.py`, `test_compression_policy.py`).
- `.env.example`, README, architecture HTML (session flow).

### Excludes

- `TierResolver` (low priority per feature-053 matrix).
- Persistence across workers (sessions remain in-memory).
- Redis-backed session store.
- Presidio / ingestion changes.

## Functional Requirements

- **FR-01:** When compression disabled, behavior identical to current sliding window.
- **FR-02:** Heuristic anchor detects budget/hour/deadline/scope patterns (ported positive/negative cases).
- **FR-03:** Non-anchor turns beyond window fold into cumulative summary prepended to context.
- **FR-04:** Anchor turns always appear verbatim in `to_messages_list()`.
- **FR-05:** Summarizer failure logs warning and keeps raw turns (no session crash).
- **FR-06:** Integration test: 15+ turns with anchor fact in turn 2 still present in messages after compression.
- **FR-07:** Session API response shape unchanged except optional `compression_summary` debug field when `dev_mode`.

## Technical Approach

### Module layout

```text
app/services/conversation_compression/anchors.py
app/services/conversation_compression/summarizer.py
app/services/conversation_compression/policy.py
app/services/sessions.py                    # integrate CompressedConversationHistory
app/routers/sessions.py
app/config.py
tests/test_conversation_compression_anchors.py
tests/test_conversation_compression_policy.py
tests/test_session_compression_integration.py
```

### Compression flow

```text
on add_user_message:
  policy.evaluate → anchor | summarize_into_running | evict_oldest_pair
to_messages_list:
  [system] + [summary user block?] + [anchor turns] + [recent window]
```

### Settings preview

```text
CONVERSATION_COMPRESSION_ENABLED=false
ANCHOR_DETECTOR_MODE=heuristic
COMPRESSION_MODEL=
COMPRESSION_MAX_SUMMARY_TOKENS=512
```

## Acceptance Criteria

- [ ] **AC-01:** Heuristic anchor positive/negative cases pass (ported fixtures).
- [ ] **AC-02:** Policy preserves anchor turn after 15 synthetic turns (AC-19 from feature-053).
- [ ] **AC-03:** Compression disabled → byte-identical message list vs current `ConversationHistory` for fixture.
- [ ] **AC-04:** Summarizer mocked in fast suite; live marked `@pytest.mark.slow`.
- [ ] **AC-05:** `uv run pytest` fast suite passes.
- [ ] **AC-06:** `.env.example` documented.

## Test Plan

### Unit tests

- Anchor heuristic rules (official test cases adapted).
- Policy: anchor preserved, summary updated, window enforced.

### Integration tests

- Session router with compression enabled + mocked summarizer: long conversation estimate still includes anchor text in LLM prompt (spy on messages).

### Manual

- Swagger session multi-turn with compression on in local dev.

## Verification

| Check | Command |
| --- | --- |
| Anchors | `uv run pytest tests/test_conversation_compression_anchors.py -q` |
| Policy | `uv run pytest tests/test_conversation_compression_policy.py -q` |
| Integration | `uv run pytest tests/test_session_compression_integration.py -q` |
| Regression | `uv run pytest tests/test_sessions*.py -q` |

**Not verified yet:** live summarization quality; cross-worker session behavior (out of scope).

## Documentation Plan

| Artifact | Update |
| --- | --- |
| `.env.example` | Compression settings |
| `README.md` | Session compression section |
| `docs/arquitectura-estimador-cag.html` | Session memory diagram |

## Implementation Plan

- [ ] **Step 1:** `AnchorDetector` heuristic port (TDD).
- [ ] **Step 2:** `CumulativeSummarizer` + mocks.
- [ ] **Step 3:** `CompressionPolicy` orchestration.
- [ ] **Step 4:** Wire into `ConversationHistory` / sessions router.
- [ ] **Step 5:** Integration test + docs.

## Estimation

- Size: **M**
- Estimated time: **4–6 hours**
- Planned steps: **5**

## Pull Request

- Draft: https://github.com/povedica/master-ia-lidr/pull/57
- Branch: `feature/064-conversation-compression-s05`

## How to start

```text
/start-task docs/work-items/feature-064-conversation-compression-s05.md
```

Parent: `docs/work-items/feature-053-official-master-parity-alignment.md` Phase 4.
No hard prerequisite; can parallelize with `feature-063` in separate worktree (`mutex_group: session-memory`).
