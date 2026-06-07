# commit-pending

## Purpose

Create small, clear, traceable commits for `master-ia`, tied to the **master session** and the **active feature**, and record each commit where agreed (priority: the feature document). When an agent runs this command end-to-end, **always finish with `git push`** to `origin` (see Phase 7); if push is impossible, state why and what is left for the user.

## When to use

- When there are pending changes and you want to close them with ordered commits.
- After updating notes, architecture, or documentation with `/update-docs`.
- When you want academic traceability for a session or a specific feature.

## Project rules

- **Canonical work item + branch (mandatory for `/start-task` driven work):** the active work item is the **same Markdown file** passed to `/start-task` (mirror: `docs/work-items/<type>-<NNN>-<slug>.md`). The current git branch **must** match `/start-task` Phase 4.1 (e.g. `feature-014-remove-v2-estimate-stream-route.md` → `feature/014-remove-v2-estimate-stream-route`). If `git branch --show-current` does not match, **rename** (`git branch -m …`) or recreate the branch from `main` and cherry-pick—do not leave ad-hoc names (`feature/remove-…`, `feature/015-…` for a 014 doc, etc.).
- **Single commit log until the feature is closed:** append **every** new commit row to **`## Repository commits (master-ia)`** in **that** canonical file only. **Do not** record this feature’s commits in a different work item’s table unless the operator explicitly switches the active canonical document and branch.
- **Work item document (priority):** append the commit log to the active work item document when it exists and is clear (by convention: `learnings/second-brain-master-ia/proyectos/<project>/work-items/<type>-<NNN>-*.md` or an explicit path you give).
- **Master session:** keep a link to the session (`learnings/second-brain-master-ia/sesiones/sesion-NN-*.md` or equivalent) for context and a duplicate table or summary **when** it applies; if work is feature-only, the main table may live **only** in the feature doc.
- **If the log destination is unclear:** default to `docs/work-items/chore-changes-refs.md` unless the user gives a different destination. Create it if it does not exist.
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

**Preferred destination:** the active work item file (e.g. `docs/work-items/feature-012-configuracion-inicial-cag.md`). **Fallback for unassigned repo workflow/chore changes:** `docs/work-items/chore-changes-refs.md`. **Optional secondary:** the active session note, with a link to the work item if you want to avoid duplicating rows.

---

## Mandatory flow

### Phase 0. Identify where to log (work item + session)

1. **Active work item:** find the canonical document under `docs/work-items/feature-NNN-<slug>.md`. That is the **only** default place for `## Repository commits (master-ia)` for this feature (or the existing Spanish heading `## Commits del repositorio (master-ia)`—normalize to English when you next edit that section). Confirm the current branch matches Phase 4.1 of `/start-task` for that filename.
2. **Session:** locate `learnings/second-brain-master-ia/sesiones/sesion-NN-*.md` if it applies.
3. **If the work item doc is missing or ambiguous:** use `docs/work-items/chore-changes-refs.md` as the default log destination for unassigned repo workflow/chore changes, unless the user explicitly chooses another document.

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

- clean tree (no uncommitted task-related files; intentional unrelated leftovers must be explicit)
- commits are clear and small
- feature table (and session, if used) lists every new hash

### Phase 7. Push to remote (mandatory)

**Agents executing this command must always run a push at the end** once commits are created and the working tree is in the intended state. Do not stop after Phase 6 without attempting push unless there is no `origin`, no network, or the user has explicitly asked not to push.

```bash
git push -u origin HEAD
```

If the remote rejects the push, sync with `git pull --rebase` and push again. If push still fails, document the error and leave the branch ready for a manual push.

---

## Golden rules (commit report)

| Situation | Action |
|-----------|--------|
| Branch mismatch vs `/start-task` Phase 4.1 | **Rename** the branch (`git branch -m …`) or recreate from `main` and cherry-pick; do not commit on ad-hoc names. |
| Known work item | Always update `## Repository commits (master-ia)` (or normalize an existing Spanish-titled section) in **that** work item `.md` only for this feature’s commits. |
| Unknown work item | Log to `docs/work-items/chore-changes-refs.md` by default unless the user gives another destination. |
| Mixed work (master-ia + notes outside the repo) | Commit only what lives in the repo; the log table may live in Second Brain even when those files are not in `git`. |

## Checklist

- [ ] Canonical branch name matches the work item file (`feature/NNN-slug` per `/start-task` Phase 4.1).
- [ ] Commit log destination agreed (feature doc by default, or ask + suggest).
- [ ] No secrets or local artifacts in staging.
- [ ] Each commit has a single reasonable focus.
- [ ] Applicable validations were run.
- [ ] Every commit appears in the **feature document table** (or agreed location).
- [ ] **`git push` to `origin` attempted and completed**, or failure explained with next step (mandatory for agent runs of this command).

## Related

- [`update-docs`](update-docs.md)
- [`session-review`](session-review.md)
- [`master-tutor`](master-tutor.md)

**Last updated:** 2026-05-17
