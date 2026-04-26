# write-feature

## Purpose
Create a concise feature specification before implementation.

## When to Use
Use for a new API endpoint, service, LLM workflow, script, project setup, or reusable capability.

## Destination
Prefer one of:
- `second-brain-master-ia/proyectos/estimador-cag/decisiones/`
- `second-brain-master-ia/proyectos/estimador-cag/sesiones/`

Use the active session when the feature belongs to a class or practice session.

## Required Workflow
1. Read relevant rules:
   - `.cursor/rules/00-base-standards.mdc`
   - `.cursor/rules/02-fastapi-standards.mdc` when API work is involved
   - `.cursor/rules/03-ai-engineering-standards.mdc` when LLM work is involved
   - `.cursor/rules/04-environment-and-secrets.mdc` when settings or secrets are involved
   - `.cursor/rules/05-testing-standards.mdc`
2. Gather context from existing code and docs.
3. Write one canonical feature document.
4. Include baby steps and verification.
5. Do not implement the feature unless the user explicitly asks.

## Required Structure
```markdown
# Feature: [Name]

## Objective
What is being built and why.

## Context
Existing code, similar patterns, constraints.

## Scope
### Includes
- ...

### Excludes
- ...

## Functional Requirements
Concrete behavior, inputs, outputs, and examples.

## Technical Approach
FastAPI route, service, LLM client, settings, data flow.

## Acceptance Criteria
- [ ] ...

## Test Plan
- Unit tests:
- Integration tests:
- Manual checks:

## Documentation Plan
What must be reflected in README or Second Brain.
```

## Rules
- Keep specs short enough to implement from.
- Include `uv` commands when execution is relevant.
- Mention environment variables if the feature uses external APIs.
- Never include real API keys in the document.
