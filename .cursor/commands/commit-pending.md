# commit-pending

## Purpose

Create small, clear, traceable commits for `master-ia`, tied to the **master session** and the **active feature**, and record each commit where agreed (priority: the feature document).

## When to use

- When there are pending changes and you want to close them with ordered commits.
- After updating notes, architecture, or documentation with `/update-docs`.
- When you want academic traceability for a session or a specific feature.

## Project rules

- **Feature document (priority):** append the commit log to the active feature document when it exists and is clear (by convention: `second-brain-master-ia/proyectos/<project>/decisiones/feature-*.md` or an explicit path you give).
- **Master session:** keep a link to the session (`second-brain-master-ia/sesiones/sesion-NN-*.md` or equivalent) for context and a duplicate table or summary **when** it applies; if work is feature-only, the main table may live **only** in the feature doc.
- **If the log destination is unclear:** **do not run `git commit` until you ask** where to record the report. Always give an **explicit default suggestion**, for example:
  - *"I suggest logging commits in `second-brain-master-ia/proyectos/<project>/decisiones/<active-feature>.md` and, if you want class traceability, a short summary in `sesiones/sesion-NN-*.md`."*
- **Size:** aim for up to **5 files** and **~200 lines** per commit, unless the change is one indivisible logical block (e.g. initial scaffold) and is explained in the report itself.
- **Messages:** **English**, conventional prefix: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.
- **Commit log table:** write **English** prose in the description column (and English section headings when you create them), per `.cursor/rules/00-base-standards.mdc`. Commit subjects stay as in Git (English).

## Standard table (paste into the destination document)

```markdown
## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `abc1234` | `docs(cursor): example message` | Brief English description of what changed. |
```

**Preferred destination:** the active feature file (e.g. `decisiones/feature-configuracion-inicial-cag.md`). **Optional secondary:** the active session note, with a link to the feature if you want to avoid duplicating rows.

---

## Mandatory flow

### Phase 0. Identify where to log (feature + session)

1. **Active feature:** find the canonical feature document (e.g. under `second-brain-master-ia/proyectos/estimador-cag/decisiones/`). That is the default place for `## Repository commits (master-ia)` (or the existing Spanish heading `## Commits del repositorio (master-ia)`—normalize to English when you next edit that section).
2. **Session:** locate `second-brain-master-ia/sesiones/sesion-NN-*.md` if it applies.
3. **If the feature doc is missing or ambiguous:** stop, **ask** where to log the report, and always include a **concrete suggestion**. Do not run `git commit` until the destination is confirmed.

### Phase 1. Review pending state

```bash
git status
git status --short
git diff --stat
```

Note:

- modified, new, and deleted files
- mix of code, docs, and configuration
- whether to split into more than one commit

### Phase 2. Catch files that must not be committed

Check for items that belong in `.gitignore` instead of Git:

- secrets: `.env`, `.env.local`, credentials, tokens
- caches or runtime: `.venv/`, `__pycache__/`, `*.pyc`, logs
- local artifacts: `.DS_Store`, `.idea/`, `Thumbs.db`
- user-specific files you should not version

If you find any:

1. Tell the user before continuing.
2. Propose adding them to `.gitignore`.
3. Do not include them in any commit until resolved.

### Phase 3. Group commits

Group by focus:

- `feat`: new functionality
- `fix`: correction
- `docs`: README, Cursor commands, technical notes
- `test`: new or expanded tests
- `chore`: tooling, Docker, config, housekeeping
- `refactor`: internal improvement without expected behavior change

Write the commit plan first: tentative message + files per commit.

### Phase 4. Quality gates

Do not invent checks the repo does not have. Use only what truly applies to `master-ia`.

#### If you touched Python or dependencies

```bash
uv sync
```

If a test command exists, run it too.

#### If you touched Docker

```bash
docker compose config
```

If the change affects build or runtime:

```bash
docker compose build
```

#### If there is no automated suite

Say so explicitly and do a minimal manual check if it applies.

### Phase 5. Commit

For each group:

1. `git add` only the files for that commit.
2. Create the commit with an English semantic message.
3. Get the short hash:

```bash
git rev-parse --short HEAD
```

4. **Append one row** to the table in the **feature document** agreed in Phase 0 (mandatory when the feature is identified).
5. If it applies, update the session with a summary or link to the feature to avoid duplicating tables.

Example messages:

- `feat(api): add study endpoint scaffold`
- `fix(docker): copy readme before uv sync`
- `docs(cursor): add estimador-cag rules and commands`
- `chore(repo): add cursor plans directory`

### Phase 6. Final verification

```bash
git status
git log --oneline -n 10
```

Confirm:

- clean tree or intentional leftovers
- commits are clear and small
- feature table (and session, if used) lists every new hash

### Phase 7. Push to remote

```bash
git push -u origin HEAD
```

If the remote rejects the push, sync with `git pull --rebase` and push again.

---

## Golden rules (commit report)

| Situation | Action |
|-----------|--------|
| Known feature | Always update `## Repository commits (master-ia)` (or normalize an existing Spanish-titled section) in that feature `.md`. |
| Unknown feature | **Ask** where to log; **suggest** `decisiones/feature-<name>.md` under the project in Second Brain, or `sesiones/sesion-NN-*.md` as secondary. |
| Mixed work (master-ia + notes outside the repo) | Commit only what lives in the repo; the log table may live in Second Brain even when those files are not in `git`. |

## Checklist

- [ ] Commit log destination agreed (feature doc by default, or ask + suggest).
- [ ] No secrets or local artifacts in staging.
- [ ] Each commit has a single reasonable focus.
- [ ] Applicable validations were run.
- [ ] Every commit appears in the **feature document table** (or agreed location).
- [ ] `git push` to `origin` completed or error explained.

## Related

- [`update-docs`](update-docs.md)
- [`session-review`](session-review.md)
- [`master-tutor`](master-tutor.md)

**Last updated:** 2026-04-26
