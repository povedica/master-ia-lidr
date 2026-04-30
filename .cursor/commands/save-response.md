# save-response

## Purpose

Create a **markdown file** under `output-responses/` at the repository root from **raw text or structured content** the user supplies in the same message (or immediately after invoking the command). The file name **must include date and time** so outputs do not overwrite each other.

## When to use

- After an LLM or estimation reply that the user wants preserved locally for reading, diffing, or sharing outside Git.
- When the user pastes a long response and asks to save it as `.md`.
- Together with `/save-response` and the body in one turn, or `/save-response` plus pasted content.

## Command input

The user passes the **markdown or plain text** to store. Optional: a short **title prefix** or **slug** for the file stem (before the timestamp).

Examples:

```text
/save-response

## My notes
- Item one
```

```text
/save-response coffee-mvp

(paste estimation markdown here)
```

If no slug is given, default the stem to `response`.

## Output location and naming

- **Directory:** `output-responses/` (repo root). Create it if missing.
- **File name (required pattern):** `{stem}-{YYYYMMDD}-{HHMMSS}.md`
  - Example: `response-20260429-143052.md`
  - Example with slug: `coffee-mvp-20260429-143052.md`
- **Timestamp source:** Use the **current** local date and time when the file is written. Prefer a shell one-liner from the repo root so the agent does not guess the clock, for example:

```bash
date '+%Y%m%d-%H%M%S'
```

Build the full path as:

```text
output-responses/{stem}-{YYYYMMDD}-{HHMMSS}.md
```

Use only safe filename characters for `{stem}`: lowercase letters, digits, and hyphens (normalize spaces to hyphens, collapse multiple hyphens).

## Content rules

1. **Preserve meaning** of the user input; fix obvious typos only if the user asks.
2. **Improve readability** when the input is dense or escaped:
   - Use proper `#` / `##` / `###` headings where structure is clear.
   - Normalize tables to valid GitHub-flavored markdown.
   - Add horizontal rules `---` between major sections if it helps scanning.
3. If the input is already well-formatted markdown, **minimal edits** (do not rewrite unnecessarily).
4. Optional first line in the file:

```markdown
**Saved:** YYYY-MM-DD HH:MM (local)
```

(use the same moment as the filename timestamp, human-readable)

## Git and privacy

- `output-responses/` is listed in `.gitignore`; files there are **local only** and must not be `git add`’d unless the user explicitly changes ignore rules.
- Do not embed secrets, API keys, or personal data the user did not intend to save.

## Agent checklist

- [ ] Obtained or inferred `{stem}` (`response` if absent).
- [ ] Resolved timestamp via `date` (or equivalent), not a hardcoded guess.
- [ ] Wrote `output-responses/{stem}-{YYYYMMDD}-{HHMMSS}.md`.
- [ ] Reported the **full path** back to the user.

## Related

- `commit-pending` — do not commit `output-responses/` contents by default.

---

**Last updated:** 2026-04-29
