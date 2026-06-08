---
name: validation-pass-fastapi
description: Run a focused validation pass for FastAPI and Python work in master-ia. Use after implementation or before committing when checking tests, startup commands, docs sync, .env.example changes, and definition-of-done readiness.
---

# Validation Pass FastAPI

Use this skill after coding to verify that a task is actually ready to close.

## Scope

Best for:

- FastAPI route or service changes
- settings/config updates
- README or workflow updates tied to code
- `estimador-cag` and similar Python subprojects

## Validation flow

1. Identify the smallest meaningful checks.
2. Run repo-native validation only:
   - `uv sync`
   - `uv run pytest` (default fast suite; `slow` tests deselected — see `spec-001-pytest-heavy-test-opt-in.md`)
   - `uv run pytest --run-heavy -m slow` only when the task explicitly requires live/heavy eval verification
   - `uv run uvicorn app.main:app --reload` when runtime behavior matters
3. Confirm:
   - no real secrets committed
   - `.env.example` updated if needed
   - docs aligned with behavior
   - remaining risks are explicit

## Output template

```markdown
## Validation Pass
- Checks run:
- Checks passed:
- Checks not run:
- Docs updated:
- Remaining risks:
- Ready for `check-dod` / `commit-pending`:
```

## Related commands

- `testing`
- `check-dod`
- `finish-task`
- `commit-pending`
