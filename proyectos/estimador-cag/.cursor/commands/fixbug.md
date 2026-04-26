# fixbug

## Purpose
Fix bugs through reproduction, root cause analysis, minimal change, and verification.

## Workflow
1. Describe observed behavior.
2. Describe expected behavior.
3. Reproduce with a failing test when practical.
4. Identify root cause.
5. Implement the smallest fix.
6. Add or update regression coverage.
7. Document the fix in the active session or project bug note.

## Bug Note Template
```markdown
# Bug: [Name]

## Problem
What failed and where.

## Root Cause
Why it failed.

## Fix
What changed.

## Verification
Commands, tests, or manual checks.

## Regression Risk
What could break again.
```

## Rules
- Do not patch symptoms without naming the root cause.
- Mock external APIs when the bug involves provider calls.
- Do not require real OpenAI calls to verify a bug fix unless explicitly needed.
- Never log or expose API keys while debugging.
