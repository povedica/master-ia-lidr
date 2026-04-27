# requirement-validate

## Purpose
Review a requirement document for completeness, risks, and implementation readiness without creating bureaucracy.

## When to Use
- Before implementation starts.
- When a feature document feels vague or oversized.
- After `requirement-write` and before `requirement-design`.

## Workflow
1. Read the canonical requirement document.
2. Classify the work:
   - `feature`
   - `hotfix`
   - `case`
   - `experiment`
3. Validate:
   - objective clarity
   - bounded scope
   - acceptance criteria
   - verification path
   - documentation destination
   - secret/config impact
4. Produce a short validation report with:
   - strengths
   - missing pieces
   - risks
   - suggested defaults
   - proceed / refine recommendation

## Rules
- Analysis informs, never blocks.
- Never say "cannot proceed" unless the task is unsafe or implies secret leakage.
- Ask only for truly blocking decisions.
- Prefer concrete defaults over open-ended questions.

## Recommended Output
```markdown
## Validation Summary
- Ready:
- Risks:
- Missing:
- Suggested defaults:
- Proceed recommendation:
```

## Related
- `requirement-write`
- `requirement-design`
- `start-task`
