# refactor

## Purpose
Improve code structure without changing behavior.

## Workflow
1. Identify the code smell, duplication, or unclear boundary.
2. Confirm current behavior.
3. Define the smallest refactor step.
4. Run related tests or a manual baseline.
5. Refactor one step.
6. Verify behavior remains unchanged.
7. Document any architectural decision if relevant.

## Rules
- Do not combine refactor with new feature behavior.
- Keep provider boundaries intact.
- Prefer clarity over clever abstraction.
- Move notebook logic into reusable modules only when it is needed by scripts, API, or tests.
- Stop if tests or manual checks fail and fix the failure before continuing.
