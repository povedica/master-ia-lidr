# requirement-design

## Purpose
Turn a validated requirement into a technical design that is small, testable, and aligned with the current repo.

## When to Use
- The task touches multiple files or layers.
- You need to decide boundaries before coding.
- A feature doc exists but the implementation shape is still unclear.

## Workflow
1. Read the canonical requirement document.
2. Read only the relevant rules and similar local code.
3. Define:
   - target files
   - data flow
   - boundaries between router/service/config/docs/tests
   - verification strategy
   - documentation impact
4. Keep the design proportional to the task.
5. Record trade-offs and rejected alternatives when they matter.

## Rules
- Reuse existing repo patterns before introducing new structure.
- Do not import enterprise DDD/CQRS patterns unless the task clearly needs them.
- Prefer explicit provider boundaries, simple routing, and documented settings.
- If the task is tiny, collapse design into a short implementation note.

## Suggested Sections
- `## Design Summary`
- `## Target Files`
- `## Data Flow`
- `## Verification`
- `## Risks / Trade-offs`

## Related
- `requirement-tasks`
- `check-architecture`
- `start-task`
