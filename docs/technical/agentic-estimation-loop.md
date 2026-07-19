# Agentic estimation loop (Session 12 / feature-054)

Living technical reference for the **hand-written agentic estimation loop** in `master-ia`. This path is **additive**: it does not replace the fixed RAG pipeline (`POST /api/v1/estimate/rag`) or CAG v2.

**Work item:** [feature-054-agentic-estimation-loop.md](../work-items/feature-054-agentic-estimation-loop.md)  
**Session note:** [learnings/docs/sesiones/sesion-12-agentic-estimation-loop.md](../../learnings/docs/sesiones/sesion-12-agentic-estimation-loop.md)  
**Official reference:** `ai-engineering` branch `session_12` (`estimator/app/generation/agentic/*`)

---

## Purpose

Demonstrate that an agent is a **controlled loop** you own:

1. Call an LLM with tool schemas.
2. Execute tool calls the model requests.
3. Return observations and chain with `previous_response_id`.
4. Stop when the model stops calling tools (or hit `max_iterations`).
5. Parse a final structured estimate.

Unlike `RagEstimationService`, the agent **decides** how many retrieval searches to run and in what order, based on transcript decomposition.

---

## Surfaces

| Surface | Path / command | Retrieval backend |
| --- | --- | --- |
| HTTP API | `POST /api/v1/estimate/agent` | `RetrievalService` via `build_retrieval_backend()` (needs `DATABASE_URL` + corpus) |
| CLI | `uv run python app/scripts/run_agent_s12.py <transcript> [--stub]` | `--stub` → `exercises/session-12/reference_retrieval.py`; else DB session |
| Library | `run_estimation_agent(...)` | Injectable `RetrievalBackend` callable |

**Not wired:** React `web/` UI, semantic cache, ACB, v2 guardrails, `ESTIMATE_API_KEY` / rate limits (see [Security boundaries](#security-boundaries)).

---

## Module map

```text
app/services/agentic/
├── agent_schemas.py      # Tool args, AgentStep, AgentTrace, AgentEstimate, AgentRunResult
├── agent_tools.py        # TOOL_SCHEMAS (flat, strict), dispatch_tool, calculate_estimate, validate_estimate
├── retrieval_adapter.py  # map_retrieval_row_to_item, build_retrieval_backend, load_stub_retrieval_backend
├── agent_loop.py         # run_estimation_agent, SYSTEM_PROMPT, Responses API loop
└── openai_client.py      # get_async_openai_client (AsyncOpenAI, not LiteLLM)

app/routers/agent_estimations.py
app/schemas/agent_estimation_response.py
app/scripts/run_agent_s12.py

exercises/session-12/
├── sample_transcript_simple.txt
├── sample_transcript_complex.txt
├── reference_retrieval.py
├── calculate_estimate_skeleton.py
└── README.md
```

---

## Deliberate fork decisions

| Topic | `master-ia` choice | Rest of repo |
| --- | --- | --- |
| LLM transport | Raw `AsyncOpenAI().responses.create` / `.parse` | LiteLLM + Instructor (`complete_structured`) |
| Logging | stdlib `logging` + stable `extra` keys | Same pattern as feature-052+ |
| Retrieval | `RetrievalService.retrieve()` + `ChunkContentRepository` | Same hybrid pipeline as RAG estimate |
| Final schema | Light `AgentEstimate` (no per-line `SourceCitation`) | Heavy `RagEstimationResult` with citation audit |
| structlog | **Not used** | Official `session_12` uses structlog |

Do not route the agent loop through `LLMPipeline`, semantic cache, or ACB without an ADR.

---

## Tools

### `search_budgets(query, filters?)`

- **Purpose:** Retrieve historical budgets for **one** component.
- **Backend:** `RetrievalBackend` — async `(SearchBudgetsArgs) -> list[dict]`.
- **Default:** `build_retrieval_backend()` wraps `RetrievalService.retrieve()`; maps rows + chunk content to stub-compatible items.
- **Stub:** `load_stub_retrieval_backend()` → keyword corpus in `exercises/session-12/reference_retrieval.py`.
- **Return item shape:**

```json
{
  "id": 1001,
  "content_preview": "...",
  "sector": "logistics",
  "budget_id": "BUD-CORE-2023-02",
  "estimated_hours": 1150.0,
  "distance": 0.12
}
```

`estimated_hours` comes from chunk metadata (`estimated_hours`); `distance` from rerank/fusion/score.

### `calculate_estimate(components)`

- **Purpose:** Deterministic partial/total hours (median + `CONTINGENCY_FACTOR` 0.15).
- **Pure Python** — no LLM. Empty `reference_amounts` → `unbudgeted=True`, `0` hours (no invented numbers).

### `validate_estimate(components, total_hours)` (optional guardrail)

- Flags unbudgeted components, hours outside reference range, total mismatch, non-positive or implausible totals.
- Invoked in `SYSTEM_PROMPT` as the last tool step before final answer.

### Responses API schemas

Flat function definitions with `"strict": true` and `"additionalProperties": false` at every object level. **Not** the Chat Completions nested `"function"` shape.

---

## Loop mechanics

```mermaid
sequenceDiagram
    participant CLI as CLI / HTTP
    participant Loop as run_estimation_agent
    participant OAI as OpenAI Responses API
    participant Tools as dispatch_tool

    CLI->>Loop: transcript + backend
    Loop->>OAI: responses.create(instructions, tools, user transcript)
    loop While function_call items
        OAI-->>Loop: reasoning + function_call(s)
        Loop->>Tools: dispatch_tool(name, args, backend)
        Tools-->>Loop: result dict + summary
        Loop->>Loop: append AgentStep to trace
        Loop->>OAI: responses.create(previous_response_id, function_call_output)
    end
    Loop->>OAI: responses.parse(text_format=AgentEstimate)
    OAI-->>Loop: AgentEstimate
    Loop-->>CLI: AgentRunResult(estimate, trace, iterations, stopped_reason)
```

**Stopping reasons:** `completed`, `max_iterations`, `no_final_estimate`.

**Error handling:** Malformed JSON args or tool exceptions become `{"error": "..."}` observations; the loop does not crash.

**Parallel tool calls:** One reasoning summary per turn; siblings get `(parallel tool call in the same turn as STEP N)`.

---

## HTTP contract

### `POST /api/v1/estimate/agent`

**Request** (`AgentEstimateRequest`):

```json
{
  "transcript": "Meeting transcript text…",
  "model": "gpt-5-mini",
  "reasoning_effort": "medium",
  "max_iterations": 10
}
```

Optional fields fall back to `AGENT_*` settings.

**Response** (`AgentEstimateResponse`):

```json
{
  "result": {
    "components": [
      {
        "name": "Business backend",
        "estimated_hours": 1265.0,
        "rationale": "…",
        "cited_chunk_ids": [2001, 2002]
      }
    ],
    "total_hours": 4500.0,
    "assumptions": ["…"],
    "confidence": "medium"
  },
  "trace": { "steps": [ … ] },
  "request_id": "…",
  "iterations": 5,
  "stopped_reason": "completed",
  "model": "gpt-5-mini"
}
```

**503** when `OPENAI_API_KEY` is missing.

---

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `AGENT_MODEL` | `gpt-5-mini` | Default Responses API model |
| `AGENT_REASONING_EFFORT` | `medium` | `reasoning.effort` (`minimal` \| `low` \| `medium` \| `high`) |
| `AGENT_MAX_ITERATIONS` | `10` | Hard cap on Responses round-trips |
| `AGENT_RETRIEVAL_MODE` | *(empty)* | Override retrieval mode for `search_budgets`; empty → `RAG_ESTIMATION_RETRIEVAL_MODE` |
| `OPENAI_API_KEY` | *(required for live runs)* | Agent path only; not used by default test suite |
| `OPENAI_TIMEOUT_SECONDS` | `30` | AsyncOpenAI client timeout; raise to ~600 for `gpt-5` + `medium` deliverable runs |
| `DATABASE_URL` | *(empty)* | Required for real retrieval (CLI without `--stub`, HTTP API) |
| `RAG_ESTIMATION_RETRIEVAL_MODE` | `B` | Fallback mode when `AGENT_RETRIEVAL_MODE` empty |
| `RETRIEVAL_RECALL_K` / `RETRIEVAL_TOP_K_FINAL` | `50` / `5` | Passed through to `RetrievalService.retrieve()` |

---

## CLI usage

```bash
# Cheap loop debugging (no database)
uv run python app/scripts/run_agent_s12.py \
  exercises/session-12/sample_transcript_simple.txt \
  --model gpt-5-mini --effort minimal --stub

# Real retrieval (needs DATABASE_URL + ingested corpus)
uv run python app/scripts/run_agent_s12.py \
  exercises/session-12/sample_transcript_simple.txt \
  --model gpt-5-mini

# Deliverable trace file (live API cost; longer timeout for gpt-5)
OPENAI_TIMEOUT_SECONDS=600 uv run python app/scripts/run_agent_s12.py \
  exercises/session-12/sample_transcript_complex.txt \
  --model gpt-5 --effort medium --stub \
  --out /tmp/agent_trace_complex.txt
```

Trace format (`AgentTrace.render()`):

```text
STEP 1
  reasoning:   Decomposing transcript into backend, ERP, mobile app…
  action:      search_budgets({"query": "…", "filters": null})
  observation: 2 historical items for '…'; hours=[1150.0, 940.0]
```

Do **not** commit generated trace files under `evaluation/**/results/`.

---

## Testing

Default CI uses **mocked** OpenAI Responses client — no API keys.

```bash
uv run pytest tests/test_agent_schemas.py tests/test_agent_tools.py \
  tests/test_retrieval_adapter.py tests/test_agent_loop.py \
  tests/test_agent_estimations_router.py tests/exercises/test_session_12_assets.py -q
```

| Test file | Focus |
| --- | --- |
| `test_agent_schemas.py` | `AgentTrace.render()` STEP N format |
| `test_agent_tools.py` | Deterministic tools, schemas, dispatch |
| `test_retrieval_adapter.py` | Row → historical item mapping |
| `test_agent_loop.py` | Multi-turn loop, max iterations, bad args |
| `test_agent_estimations_router.py` | HTTP 503 without key, 200 with mocked run |

**RAG regression:** `tests/test_rag_estimation_*.py` must stay green (agent is additive).

**Slow / live:** Manual runs with real `OPENAI_API_KEY`; optional future `@pytest.mark.slow` integration test.

---

## Security boundaries

| Control | `POST /api/v1/estimate/rag` | `POST /api/v1/estimate/agent` |
| --- | --- | --- |
| `ESTIMATE_API_KEY` | Optional (feature-056) | **Not applied** (local dev / exercise) |
| Rate limit (`RATE_LIMIT_ENABLED`) | 10/min per key bucket | **Not applied** |
| Input guardrails / semantic cache | N/A (by design) | N/A |

Hardening the agent endpoint is a follow-up (e.g. extend feature-056 scope).

---

## Comparison: fixed RAG vs agentic loop

| Aspect | Fixed RAG (`/estimate/rag`) | Agentic (`/estimate/agent`) |
| --- | --- | --- |
| Orchestration | Single pipeline: reformulate → retrieve → generate | Model-driven tool loop |
| Retrieval calls | One (composed query) | One per component (typical) |
| LLM stack | LiteLLM + Instructor | OpenAI Responses API direct |
| Output | `RagEstimationResult` + citation/coherence reports | `AgentEstimate` + `AgentTrace` |
| Pedagogical focus | Grounding + audit | Loop visibility + tool design |
| Web UI | Yes (RAG citations tab) | No (CLI / API only) |

---

## Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `503` OpenAI key not configured | Missing `OPENAI_API_KEY` | Set in `.env` |
| CLI errors without `--stub` | No `DATABASE_URL` | Use `--stub` or start Postgres + ingest |
| Empty `search_budgets` results | Empty corpus or wrong mode | Ingest budgets; try mode `B`; use `--stub` to validate loop |
| `stopped_reason=max_iterations` | Model keeps calling tools | Tune tool descriptions; increase cap temporarily |
| `no_final_estimate` | Final `responses.parse` failed | Check logs `agent_final_parse_failed`; inspect trace |

---

## Related documentation

- [docs/technical/README.md](./README.md) §25e — summary in technical baseline
- [docs/arquitectura-estimador-cag.html](../arquitectura-estimador-cag.html) — interactive architecture (router + service nodes)
- [README.md](../../README.md) — quick start commands
- [feature-053 parity matrix](../work-items/feature-053-official-master-parity-alignment.md) — Session 12 track (out of parity critical path)
