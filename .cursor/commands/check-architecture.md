# check-architecture

## Purpose
Check whether a change respects the intended boundaries and patterns of `master-ia`.

## When to Use
- New API endpoints or services.
- Refactors that move responsibilities between modules.
- Any change that introduces a new layer, package, or workflow.

## Review Focus
- router vs service vs config responsibilities
- provider/API isolation
- settings and secret handling
- testability of the design
- proportionality of abstractions
- consistency with existing repo structure

## Rules
- In `master-ia`, prefer simple FastAPI/service boundaries over heavy frameworks.
- Reject complexity imported only because another repo uses it.
- If frontend-backend integration is involved, suggest explicit API contract checks.
- If the task is API-only or learning-oriented, keep architecture lightweight.

## Related
- `requirement-design`
- `check-quality`
- `check-performance`
