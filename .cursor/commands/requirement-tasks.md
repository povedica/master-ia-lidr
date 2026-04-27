# requirement-tasks

## Purpose
Split a designed requirement into baby steps that are easy to implement, verify, document, and commit.

## When to Use
- After `requirement-design`.
- When a task feels larger than one focused implementation step.
- Before asking the agent to code a multi-file change.

## Workflow
1. Read the requirement and design docs.
2. Break the work into ordered tasks.
3. For each task, state:
   - goal
   - files or modules
   - verification
   - docs to update
   - suggested commit type
4. Keep each task small enough for one focused implementation pass.

## Recommended Template
```markdown
### Task N: [name]

**Goal**:
**Files**:
**Verification**:
**Docs**:
**Suggested commit**:
```

## Rules
- Prefer steps of 10-30 minutes when possible.
- Split code, tests, docs, and config when that improves traceability.
- If a task grows while planning, split it again.
- Do not invent checks the repo does not have.

## Related
- `requirement-design`
- `start-task`
- `commit-pending`
