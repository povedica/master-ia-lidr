# testing

## Purpose
Run and interpret the most relevant automated or manual verification for the current task.

## When to Use
- After implementation.
- Before `/check-dod` or `/commit-pending`.
- When a task changes behavior or configuration.

## Workflow
1. Detect the smallest meaningful verification:
   - targeted test file
   - full suite
   - manual API check
   - startup command
2. Run only what truly applies.
3. Report:
   - command used
   - result
   - uncovered risks
   - next test to add if the gap is meaningful

## Rules
- Do not call real provider APIs unless the task explicitly requires it.
- Prefer focused tests before full-suite runs when scope is narrow.
- If no automated suite exists, define a concrete manual check.

## Common Commands
```bash
uv run pytest
uv run pytest -q
uv run uvicorn app.main:app --reload
```

## Related
- `linter`
- `check-dod`
- `finish-task`
