# Session 13 — Estimation flow as a LangGraph multi-agent graph

In Session 12 the estimation flow was a **hand-written agentic loop** on the Responses
API (reason → act → observe). It works, but becomes awkward once you need several
steps, conditional branches, or human review pauses.

In this session that flow becomes an **explicit LangGraph graph** that lives **inside
the AI service** (`app/services/estimation_graph/`). Externally the contract stays the
same: transcript in → structured estimate (+ `status`) out. Existing RAG / CAG /
`POST /api/v1/estimate/agent` routes stay additive.

## Live multi-agent topology (session_13_live parity)

```text
START → classifier_agent
        ──Command(goto)──▶ structure_agent
        ──edge──▶ human_gate_structure (interrupt #1)
        ──Send fan-out──▶ estimate_task_hours × N
        ──edge──▶ recover_and_handover (join + optional recovery agent)
        ──Command(goto)──▶ analysis_agent
        ──edge──▶ human_gate_analysis (interrupt #2)
        ──conditional──▶ proposal_agent | END
```

## Files in this folder

| File | Purpose |
| --- | --- |
| `sample_transcript_complex.txt` | Multi-component RUTA logistics transcript (same family as Session 12). |
| `demo_ciclo_completo.txt` | Shorter alternate transcript for a full graph cycle. |
| `README.md` | This runbook. |

Do **not** commit generated run artifacts (`*_run*.txt`, `example_run_*.txt`).

## Reference solution (in `master-ia`)

| Path | Role |
| --- | --- |
| `app/services/estimation_graph/state.py` | Typed `EstimationState` + keyed `merge_task_hours` reducer |
| `app/services/estimation_graph/build.py` | `build_graph(checkpointer)`, `fan_out_hours`, `route_after_gate2` |
| `app/services/estimation_graph/checkpointer.py` | DSN helper (+ pooled `AsyncPostgresSaver` after Step 5) |
| `app/services/estimation_graph/agents/*` | classifier, structure, gates, hours, analysis, proposal |
| `app/scripts/run_graph_s13.py` | CLI: auto-approve both gates; `--memory` / `--stub` |
| `tests/estimation_graph/` | MemorySaver e2e with faked LLM / retrieval |

HTTP `POST /api/v1/estimate/graph*` (Step 6) and FastAPI lifespan wiring (Step 5) land
separately; the CLI works offline with `--memory` without those pieces.

## How to run

```bash
# Partial-offline smoke: MemorySaver + canned per-task hours.
# Still needs OPENAI_API_KEY for classifier / structure / analysis / proposal agents.
uv run python app/scripts/run_graph_s13.py --memory --stub

# Write a local run report (do not commit the file)
uv run python app/scripts/run_graph_s13.py --memory --stub \
  --out /tmp/example_run_complex.txt

# Full path (Postgres checkpointer + real task-hours) — requires Step 5 wiring
# and an ingested historical-task corpus:
uv run python app/scripts/run_graph_s13.py \
  --out exercises/session-13/example_run_complex.txt
```

Flags:

- `--memory` — in-process `MemorySaver` (no Postgres for checkpoints).
- `--stub` — canned offline hours via monkeypatched `estimate_one` (no DB fan-out).
- `--transcript PATH` — override default complex transcript.
- `--estimation-id ID` — checkpointer `thread_id` (default `s13-<stem>`).
- `--out PATH` — write the rendered report.

### Checkpointer note

The Postgres checkpointer creates `checkpoints*` tables alongside pgvector on first
`setup()`. Use the same `DATABASE_URL` (driver token stripped to plain `postgresql://`
for psycopg3). A long human pause needs a connection pool — that is Step 5.

## Tests (network-free)

```bash
uv run pytest tests/estimation_graph tests/exercises/test_session_13_assets.py -q
```

Default suite uses `MemorySaver` + fakes — no API keys, no Postgres.

## Pedagogical takeaways

1. A multi-step estimation flow with human review is an **explicit typed graph**, not a
   black-box framework.
2. **Keyed reducers** (`merge_task_hours`) prevent duplicate rows on resume.
3. **Handovers** use `Command(goto=…, update=…)`; gates use `interrupt()` +
   `Command(resume=…)`.
4. Fan-out uses the LangGraph **Send** API; join + recovery reuses the Session 13
   two-phase agentic APIs (`run_structure_agent`, `run_task_hours_recovery_agent`).

## Technical docs

- Work item: [feature-066-langgraph-multi-agent-estimation-s13.md](../../docs/work-items/feature-066-langgraph-multi-agent-estimation-s13.md)
- Technical reference: [estimation-graph-s13.md](../../docs/technical/estimation-graph-s13.md)
- Session note: [sesion-13-langgraph-multi-agent-estimation.md](../../learnings/docs/sesiones/sesion-13-langgraph-multi-agent-estimation.md)
- Official source: `ai-engineering` branch `session_13_live`
  (`estimator/app/domain/graph/`, `estimator/scripts/run_graph_s13.py`)
