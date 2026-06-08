# CAG stress testing

Deterministic multi-turn and attachment stress runs for the session-based CAG baseline.

**Full technical reference:** [docs/technical/cag-stress-testing.md](../../docs/technical/cag-stress-testing.md)  
**Interactive guide (Spanish):** [docs/arquitectura-estimador-cag.html](../../docs/arquitectura-estimador-cag.html#stress-testing)

## Regenerate PDF fixtures

```bash
uv run python -m evals.stress.fixtures.build_pdfs
```

## Run stress suite (HTTP)

```bash
uv run uvicorn app.main:app --reload
uv run python -m evals.stress.run \
  --http http://localhost:8000 \
  --scenarios growing,pivot,contradiction \
  --attachment-sizes 0,5,20,50,100 \
  --repeats 3 \
  --write-report
```

## Deliverables

Each scenario writes its own artifacts (suffix derived from `--output` / `--report-output` stems):

- `evals/stress/results-<scenario>.csv` — one row per turn (e.g. `results-pivot.csv`)
- `evals/stress/REPORT-<scenario>.md` — summary tables and interpretation (with `--write-report`)

Legacy sample from the first HTTP run (growing only) remains as `results.csv` / `REPORT.md` in the repo.

## Request loop

The runner nests five loops (sequential — no parallelism):

```text
for scenario in --scenarios:
  for attachment_size_kb in --attachment-sizes:
    for repeat in 1..--repeats:
      for n_turns in --turn-counts:          # default: 1, 3, 6, 10, 20
        POST /api/v1/sessions                # new conversation
        for each turn in build_scenario(...):
          POST .../estimate                  # real LLM call
          GET  .../sessions/{id}             # read last_turn_observation
        append CSV rows + evaluate metrics
  write results-<scenario>.csv (+ REPORT-<scenario>.md)
```

**Default row count per scenario:** 5 attachment sizes × 3 repeats × (1+3+6+10+20) turns = **600 rows** (~1,275 HTTP requests including session create and GET).

**Stops when:** all combinations finish and artifacts are written, or on HTTP error / 120 s request timeout. It does **not** stop early on high latency or cost — those are recorded as metrics only.

**Quick smoke (one scenario, few calls):**

```bash
uv run python -m evals.stress.run \
  --in-process \
  --scenarios pivot \
  --attachment-sizes 0 \
  --turn-counts 3 \
  --repeats 1 \
  --write-report
```

## Metric defaults

- Latency budget: `4000 ms` (`--latency-budget-ms`)
- Cost budget: `$0.05` per turn (`--cost-budget-usd`)
