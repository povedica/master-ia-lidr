# Session 14 — Supervisor/Worker Estimation + Conditional HITL

Exercise track for `feature-067`: replace the Session 13 linear multi-agent graph
with an explicit supervisor and four least-privilege workers, plus conditional
human review when reliability is insufficient.

## Topology

```text
START → supervisor
  ├─ requirements_extractor (model only)
  ├─ budget_searcher (search_budgets only)
  ├─ estimate_generator (calculate_estimate only)
  ├─ coherence_validator (validate_estimate only)
  ├─ human_review [interrupt] when review policy fires
  └─ END (completed | rejected)
```

## Edge-case transcript

`sample_transcript_edge_case.txt` is authored so historical search has **no
precedent** in the stub/offline corpus. That deterministically triggers
`status="awaiting_human_review"` regardless of model variance.

## Offline pause/resume smoke

```bash
uv run python app/scripts/run_graph_s13.py \
  --memory --stub \
  --transcript exercises/session-14/sample_transcript_edge_case.txt \
  --out /tmp/supervisor_hitl_edge_case_trace.txt
```

Checklist for the local trace (do **not** commit the generated file):

1. Supervisor routes through all four workers.
2. Pause at `estimation_review` with `awaiting_human_review`.
3. Auto-resume approve decision completes the run.
4. Trace shows supervisor decisions, pause, and final status.

## Live / slow path

Needs real credentials and optionally Postgres. Prefer a longer timeout:

```bash
OPENAI_TIMEOUT_SECONDS=600 uv run python app/scripts/run_graph_s13.py \
  --transcript exercises/session-14/sample_transcript_edge_case.txt \
  --out /tmp/supervisor_hitl_live_trace.txt
```

Mark any real-provider or Postgres restart smoke as `@pytest.mark.slow` / opt-in.
