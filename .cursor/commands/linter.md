# linter

## Purpose
Run the smallest useful static validation for the files touched in the current task.

## When to Use
- Before commit.
- After larger edits.
- When the user asks for lint or compile verification.

## Workflow
1. Prefer diagnostics already available in the editor.
2. Run repo-native checks only when they exist and are relevant.
3. Report:
   - what ran
   - what passed
   - what failed
   - what was not available

## Rules
- Do not invent a linter stack the repo does not use.
- For Python work, prefer local diagnostics plus project test commands.
- If there is no dedicated lint command, say so explicitly.

## Related
- `testing`
- `check-quality`
- `check-dod`
