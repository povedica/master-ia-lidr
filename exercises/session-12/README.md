# Session 12 — Hand-written agent (manual loop on the Responses API)

The estimation system works well with a **fixed pipeline**: rephrase → retrieve → generate.
But a real transcript that mixes, for example, a business backend + ERP integration + mobile app
forces you to **search historical budgets separately for each component**, compute partials, and
consolidate. You do not know in advance how many searches you will run or in what order — it depends
on what the transcript says.

That is where an **agentic layer** adds what a fixed pipeline lacks: **deciding what to do at each
step**. In this exercise you build it **by hand, without a framework**.

> An agent is not magic. It is a loop that calls an LLM to **decide**, executes **tools**, and stops
> when done.

## What you build

An agent that receives a transcript, decomposes it into components, uses **two tools**
(`search_budgets` and `calculate_estimate`), **iterates in a manual loop** (reason → act → observe →
repeat), and returns a structured estimate **together with a trace** of its reasoning.

It lives in the **AI service** (Python + FastAPI). `search_budgets` wraps your S9–S10 retrieval —
**do not reimplement it**. `calculate_estimate` is a deterministic Python function.

## Files in this folder (starter kit)

| File | Purpose |
| --- | --- |
| `sample_transcript_simple.txt` | Single component. Cheap loop debugging with `gpt-5-mini`. |
| `sample_transcript_complex.txt` | Four distinct components. Acceptance-criteria transcript. |
| `reference_retrieval.py` | **Safety net**: canned retrieval stub without a database. Use only if your pipeline is not ready. Prefer wrapping the real pipeline. |
| `calculate_estimate_skeleton.py` | Deterministic cost skeleton with `TODO`s so you can focus on the loop. |

## The two tools (+ one optional)

Define them with **JSON Schema** and `strict: true`. On the **Responses API** the schema is **flat**
(`{"type": "function", "name": ..., "description": ..., "parameters": {...}}`), unlike Chat
Completions. Names, descriptions, and parameters **in English**.

- **`search_budgets(query, filters?)`** — retrieve historical budgets for **one** component.
  Wraps hybrid retrieval + reranking from S9–S10.
- **`calculate_estimate(components)`** — compute breakdown and total from components and reference
  amounts. Deterministic, no LLM.
- **`validate_estimate(components, total_hours)`** *(optional, recommended)* — S4-style guardrails:
  reasonable ranges, unbudgeted components, incoherent totals.

> **Tool description quality matters**: it is all the model reads to decide when to use each tool.
> Write them for a model that never sees your code.

## Drive the loop yourself

The Responses API returns `function_call` items (with `call_id`, `name`, `arguments`) and **stops
waiting for you**. That round-trip *is* the loop:

1. Scan `response.output` for `function_call`.
2. Execute the function with parsed `arguments` (JSON).
3. Return the result as `function_call_output` with the **same `call_id`**.
4. Call again chaining with `previous_response_id`.
5. Repeat while `function_call` items exist. Stop when none remain. **Set a max iteration cap** as a
   safeguard.

## Trace requirement

Per iteration: reasoning + action + observation. Minimum acceptable format:

```text
STEP 1
  reasoning:   <what the agent decided and why>
  action:      search_budgets(query="...", filters={...})
  observation: <summary of returned items>
```

## Acceptance criteria (with `sample_transcript_complex.txt`)

- Identifies **more than one component** and calls `search_budgets` **more than once**.
- Calls `calculate_estimate` with components and their references.
- Terminates on its own (no infinite loop or mid-run cut-off).
- Produces a coherent structured estimate.
- Trace shows reasoning + action + observation per step.

## Deliverable

Send Lia before the live session: (1) link to your repository with the agent inside the AI service,
and (2) the execution trace for `sample_transcript_complex.txt`.

## API cost discipline

Debug the **loop mechanics** first with `gpt-5-mini` and the simple transcript. When solid, switch to
`gpt-5` with `medium` effort for the real run on the complex transcript. Keep spend under a couple of
dollars.

---

## Reference solution (in `master-ia`)

After you try it yourself, compare with:

- `app/services/agentic/agent_schemas.py` — trace models, result, tool argument models.
- `app/services/agentic/agent_tools.py` — flat `strict:true` schemas + implementations
  (`search_budgets` wraps `RetrievalService`; `calculate_estimate` and `validate_estimate` are
  deterministic).
- `app/services/agentic/agent_loop.py` — manual loop on `client.responses.create`.
- `app/scripts/run_agent_s12.py` — runs the agent and prints the trace.

Example commands (once implemented):

```bash
# Cheap loop debugging with stub (no database)
uv run python app/scripts/run_agent_s12.py \
    exercises/session-12/sample_transcript_simple.txt --model gpt-5-mini --stub

# Deliverable run on the complex transcript
uv run python app/scripts/run_agent_s12.py \
    exercises/session-12/sample_transcript_complex.txt --model gpt-5 --effort medium \
    --out /tmp/agent_trace_complex.txt
```

Source: official `ai-engineering` branch `session_12` (`estimator/exercises/session-12/`).

**Technical reference (master-ia):** [docs/technical/agentic-estimation-loop.md](../../docs/technical/agentic-estimation-loop.md)
