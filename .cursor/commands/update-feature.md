# update-feature

## Purpose
Refine or extend an existing feature specification based on new requirements, learnings, or scope changes, keeping a single canonical document up to date.

## When to Use
Use when an already defined feature needs clarification, scope adjustment, or technical changes, but remains essentially the same capability (not a brand‑new feature).

## Input
Accept a feature file path, feature name, or natural-language update request.

If it is not clear **which document** to update (path, project, or multiple candidates), ask the user before reading or editing anything.

If the target feature is otherwise ambiguous, ask one clarifying question before editing.

## Destination
Update the same feature document you created with `/write-feature`, in its original location (work item or session file), preserving its filename and main structure.

## Required Workflow
1. Resolve the single canonical feature file to update. If you cannot identify it with confidence, stop and ask the user.
2. Read that spec end to end.
3. Gather enough context from code, docs, and Second Brain to understand the requested change.
4. Read relevant rules again if the change touches APIs, LLM workflows, environment, or tests:
   - `.cursor/rules/00-base-standards.mdc`
   - `.cursor/rules/02-fastapi-standards.mdc` when API work is involved
   - `.cursor/rules/03-ai-engineering-standards.mdc` when LLM work is involved
   - `.cursor/rules/04-environment-and-secrets.mdc` when settings or secrets are involved
   - `.cursor/rules/05-testing-standards.mdc`
   - `.cursor/rules/11-spec-system.mdc` when location, naming, or work-item structure is unclear
5. Integrate the new instructions directly into the existing sections instead of creating a new document.
6. Keep one single, coherent feature spec after the update (no duplicates).
7. Review the final document for contradictions, obsolete scope, missing acceptance criteria, and missing verification steps.
8. Do not implement the feature unless the user explicitly asks.

## Update Strategy
When applying the update instructions, follow these principles:
- Preserve the original structure and headings from the `/write-feature` template.
- Prefer editing in place over appending "Notes" at the bottom.
- Remove or rewrite any part that is now obsolete or contradicts the new direction.
- If something is uncertain, add a short "Open questions" list rather than guessing.

## Sections to Maintain
Ensure the document still matches this structure after the update (updating content as needed):

```markdown
# Feature: [Name]

## Objective
Update this section if the overall goal of the feature changes or becomes sharper.

## Context
Adjust to reflect new constraints, decisions, or related code that has appeared since the original spec.

## Scope
### Includes
Revise items that change with the new instructions.

### Excludes
Add or change exclusions when you explicitly decide not to cover something.

## Functional Requirements
Update behaviors, inputs, outputs, and examples to match the new expectations.

## Technical Approach
Adjust routes, services, LLM clients, settings, or data flows as needed.

## Acceptance Criteria
- [ ] Update checklists so they reflect the latest behavior and constraints.

## Test Plan
- Unit tests:
- Integration tests:
- Manual checks:

## Documentation Plan
Explain any new docs or changes needed in README or Second Brain.
```

## Rules
- Keep the updated spec as concise as possible while still being implementable.
- If the change is substantial, briefly summarize the main differences from the previous version in the **Context** section.
- Include or adjust `uv` commands when execution steps change.
- Mention new or changed environment variables, without ever including real secrets.
- Avoid historical clutter; the document should read as a clean, current spec rather than a change log.
- Use English for technical specs in the repo unless the user explicitly asks for a reflective Second Brain note in Spanish.

## Completion Response
When done, summarize:
- The feature document updated.
- The main spec changes.
- Any open questions or implementation risks left in the spec.
- Confirmation that no implementation was performed unless explicitly requested.

## Related
- `write-feature`
- `requirement-validate`
- `requirement-design`
- `requirement-tasks`
