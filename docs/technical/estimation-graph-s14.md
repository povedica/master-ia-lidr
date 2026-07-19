# Supervisor/worker estimation graph (Session 14 / feature-067)

Living technical reference for the **LangGraph supervisor/worker estimation
graph** in `master-ia`. This path **replaces the Session 13 internal topology**
for `/api/v1/estimate/graph*` while reusing the Postgres checkpointer, auth, and
stream/progress/proposal surfaces.

**Work item:** [feature-067-supervisor-worker-estimation-hitl.md](../work-items/feature-067-supervisor-worker-estimation-hitl.md)  
**Prior topology (superseded):** [estimation-graph-s13.md](./estimation-graph-s13.md)  
**Exercise kit:** [exercises/session-14/README.md](../../exercises/session-14/README.md)

---

## Purpose

Make dynamic routing, worker privilege, accumulated evidence, and conditional
human intervention **explicit and observable** — without growing a parallel
graph API.

---

## Topology

```text
START → supervisor
  ├─Command→ requirements_extractor ─edge→ supervisor
  ├─Command→ budget_searcher        ─edge→ supervisor
  ├─Command→ estimate_generator     ─edge→ supervisor
  ├─Command→ coherence_validator    ─edge→ supervisor
  ├─Command→ human_review [interrupt] ─edge→ supervisor
  └─Command→ END
```

Every forward business transition is `Command(goto=..., update=...)` from the
hand-written supervisor (`create_supervisor` is not used).

---

## Least privilege

| Node | Allowed capability |
| --- | --- |
| supervisor | none (routing only) |
| requirements_extractor | model / `complete_graph_structured` |
| budget_searcher | `search_budgets` only |
| estimate_generator | `calculate_estimate` only |
| coherence_validator | `validate_estimate` only |
| human_review | `interrupt()` + typed resolution fold |

---

## Conditional HITL

Human review is required when any signal is true:

- `confidence < GRAPH_HUMAN_REVIEW_CONFIDENCE_THRESHOLD` (default `0.70`)
- estimate outside historical range
- no relevant historical precedent

Pause payload gate name: `estimation_review`.  
Business `status`: `awaiting_human_review` | `completed` | `rejected`.  
Checkpointer lifecycle `state`: `paused` | `completed` (progress also has `running`).

Resume resolutions (discriminated):

```json
{"action": "approve", "comment": "..."}
{"action": "adjust", "adjusted_estimate": {"components": [], "total_hours": 420.0}}
{"action": "reject", "comment": "..."}
```

Adjust folds into state, revalidates once (`human_adjustment_validated`), then
finalizes without an infinite review loop.

---

## Module map

```text
app/services/estimation_graph/
├── state.py              # EstimationState + keyed budget_matches reducer
├── supervisor.py         # Command routing policy
├── review_policy.py      # Deterministic review signals
├── build.py              # supervisor/workers compile
├── checkpointer.py       # AsyncPostgresSaver lifecycle (unchanged)
├── structured.py         # complete_graph_structured
├── activity.py           # stream/progress didactic feed
└── agents/
    ├── requirements_extractor.py
    ├── budget_searcher.py
    ├── estimate_generator.py
    ├── coherence_validator.py
    ├── human_review.py
    └── proposal.py         # on-demand HTTP proposal helper

app/routers/estimate_graph.py
app/schemas/graph_estimation.py
app/scripts/run_graph_s13.py   # Session 14 CLI (filename kept)
exercises/session-14/
```

---

## HTTP contract

| Verb | Path | Behaviour |
| --- | --- | --- |
| POST | `/api/v1/estimate/graph` | Start → complete or pause at `estimation_review` |
| POST | `/api/v1/estimate/graph/{id}/resume` | Typed resolution; 404 unknown, 409 idle, 422 invalid |
| GET | `/api/v1/estimate/graph/{id}/state` | Snapshot; 404 unknown |
| POST | `/api/v1/estimate/graph/stream` | 202 + background `astream` |
| POST | `/api/v1/estimate/graph/{id}/resume-stream` | 202 resume in background |
| GET | `/api/v1/estimate/graph/{id}/progress` | `running` \| `paused` \| `completed` + activity |
| POST | `/api/v1/estimate/graph/{id}/proposal` | On-demand proposal from estimate + validation |

Auth: `ESTIMATE_API_KEY`. Graph unavailable → **503**; node/LLM failures → **502**.

Deliberate breaking change vs S13 business `status`:
`validated|needs_review` → `awaiting_human_review|completed|rejected`.

---

## Settings

```text
GRAPH_HUMAN_REVIEW_CONFIDENCE_THRESHOLD=0.70
GRAPH_EXTRACTION_MODEL=gpt-4o-mini
GRAPH_GENERATION_MODEL=gpt-4o
GRAPH_PROPOSAL_MODEL=gpt-4o
GRAPH_PROPOSAL_ENABLED=true
GRAPH_PERSONAS_ENABLED=true
```

---

## CLI / edge-case smoke

```bash
uv run python app/scripts/run_graph_s13.py \
  --memory --stub \
  --transcript exercises/session-14/sample_transcript_edge_case.txt \
  --out /tmp/supervisor_hitl_edge_case_trace.txt
```

Do not commit generated trace files.

---

## Tests

```bash
uv run pytest tests/estimation_graph tests/routers/test_estimate_graph.py -q
```

Default suite: MemorySaver + injected worker fakes — no API keys, no Postgres.

---

## Related

- Session 12 agent: [agentic-estimation-loop.md](./agentic-estimation-loop.md)
- Session 13 historical note: [estimation-graph-s13.md](./estimation-graph-s13.md)
- Work item: [feature-067](../work-items/feature-067-supervisor-worker-estimation-hitl.md)
