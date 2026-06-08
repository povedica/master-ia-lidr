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
  --output evals/stress/results.csv \
  --write-report
```

## Deliverables

- `evals/stress/results.csv` — one row per turn
- `evals/stress/REPORT.md` — summary tables and interpretation (generated with `--write-report`)

## Metric defaults

- Latency budget: `4000 ms` (`--latency-budget-ms`)
- Cost budget: `$0.05` per turn (`--cost-budget-usd`)
