# finish-task

## Purpose
Close a task with verification, documentation, and next steps.

## Workflow
1. Review changed files.
2. Check for secrets or local artifacts.
3. Run relevant validation directly or through:
   - `check-quality`
   - `check-architecture`
   - `testing`
   - `check-dod`
4. Run relevant commands when they apply:
   - `uv sync`
   - `uv run pytest` when tests exist
   - `uv run uvicorn app.main:app --reload` for manual API checks when relevant
5. Update documentation if behavior, setup, or architecture changed.
6. Summarize what changed, what was verified, and what remains pending.

## Checklist
- [ ] No `.env` or real secrets included.
- [ ] `.env.example` updated if settings changed.
- [ ] Tests or manual checks completed.
- [ ] Second Brain updated when session or learning changed.
- [ ] Follow-up tasks are explicit.

## Rules
- Do not mark work complete if the app cannot start and the task required runtime behavior.
- Do not hide failed checks.
- If no automated test suite exists yet, say so and perform the smallest useful manual verification.
- If requirements or design changed materially during implementation, reflect that before closing.
