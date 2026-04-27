# check-dod

## Purpose
Verify that a task is actually done against its requirement, verification plan, and documentation obligations.

## When to Use
- Before `/finish-task`.
- Before `/commit-pending`.
- After implementation and validation commands have run.

## Checklist
- [ ] Scope implemented matches the canonical document.
- [ ] Applicable tests or manual checks passed.
- [ ] No secrets or local artifacts are included.
- [ ] `.env.example` is updated if settings changed.
- [ ] Documentation was updated where required.
- [ ] Follow-up items are explicit and not hidden in the summary.

## Rules
- Do not mark work done if runtime behavior was required but never verified.
- Do not hide failed checks.
- If the task intentionally leaves follow-ups, state them explicitly.

## Related
- `finish-task`
- `testing`
- `check-quality`
- `commit-pending`
