---
name: requirement-validator-light
description: Review requirement documents and implementation requests for clarity, scope, risks, acceptance criteria, and verification readiness. Use when validating a feature note, planning work from Second Brain, or when the user asks whether a task is ready to implement.
---

# Requirement Validator Light

Use this skill to validate work items in `master-ia` without introducing unnecessary process.

## When to apply

- A task starts from `second-brain-master-ia/`.
- A feature note exists but may be incomplete.
- The user asks if something is ready to build.
- A change touches multiple files or has unclear scope.

## Validation checklist

- Is there one canonical source of truth?
- Is the objective explicit?
- Is scope bounded?
- Are acceptance criteria present or derivable?
- Is there a verification path?
- Is secret/config impact clear?
- Is documentation impact clear?

## Response style

- Lead with readiness: `ready`, `ready with risks`, or `needs clarification`.
- Flag risks, but do not block by default.
- Prefer concrete default suggestions over abstract questions.

## Output template

```markdown
## Validation Summary
- Ready:
- Risks:
- Missing:
- Suggested defaults:
- Recommended next command:
```

## Related commands

- `requirement-validate`
- `requirement-design`
- `start-task`
