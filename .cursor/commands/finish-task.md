# finish-task

## Purpose

Close work in `master-ia` with verification, documentation, evidence, and explicit follow-ups. **By default**, after Part A, complete the **Pull Request** lifecycle with GitHub CLI: mark ready if needed, merge, sync the default branch locally, and remove the feature branch—unless the user or runtime constraints explicitly opt out (see **Skip Part B** below).

This command is the union of **task closure** (quality gates, docs, risk summary) and a **default PR finish** workflow (`gh`), with a documented escape hatch when merge is not wanted or not possible.

## When to use

**Task closure (always applicable):**

- You are done implementing and need final validation and a clean handoff.
- You must record what was verified, what was not, and residual risk before moving on.

**PR completion (default when a PR exists):**

- After Part A, locate the PR for the current branch, ensure policy allows merge (approval, CI), then merge via `gh`, sync `main` (or repo default), delete the local feature branch, and prune remotes—unless **Skip Part B** applies.

If you only need to **prepare commits** without merging a PR, prefer `/commit-pending` first, then invoke this command **with an explicit opt-out** (e.g. “finish task, no PR merge”) or stop after Part A if you only wanted local closure.

---

## Prerequisites

**For local task closure:**

- Relevant project directory identified (the repository root for Estimador CAG).

**For PR completion (default path, in addition):**

- [ ] PR approved (or team policy allows merge).
- [ ] CI/CD checks passing on the PR.
- [ ] No uncommitted changes (`git status` clean) unless the task is explicitly to commit first.
- [ ] On the branch that tracks the PR (or you know the PR number).
- [ ] GitHub CLI (`gh`) installed and authenticated for automated merge steps.

---

## Step 0 — Retrospective and canonical doc (before merge)

Do **not** merge a PR and defer documentation.

1. Confirm the **canonical work-item** (single source of truth) is up to date:
   - Vault path: `learnings/second-brain-master-ia/proyectos/<project>/work-items/<type>-<NNN>-<slug>.md`
   - Mirror in this repo: `docs/work-items/` (see `11-spec-system.mdc` and `/start-task` for naming).
2. Ensure **acceptance**, **verification**, **`Repository commits (master-ia)`**, and any **retrospective / learnings** are reflected in that document (or a note explicitly linked from it), per **Phase 6–7** of `/start-task`.
3. If a learning should become repo policy, capture it in `.cursor/rules/` in a follow-up when appropriate — not as a substitute for updating the canonical doc.

```bash
git status
```

---

## Part A — Close the task (verification and gates)

### A.1 Review changed files

- Skim the diff scope; ensure no `.env`, credentials, or local-only artifacts are included.

### A.2 Run relevant validation

Run checks directly or through project commands / agents:

- `check-quality`
- `check-architecture`
- `testing`
- `check-dod`

When FastAPI or Python scope applies, you may use the **`validation-pass-fastapi`** skill for a focused pass.

### A.3 Commands (when they apply)

- `uv sync`
- `uv run pytest` when tests exist (narrower scope when verifying a single area)
- `uv run uvicorn app.main:app --reload` for manual API checks when runtime behavior is in scope (from the repository root).

### A.4 Documentation

- Update `README.md`, `.env.example`, and the canonical work-item if behavior, setup, or architecture changed.
- Update Second Brain / session material when the session or learning outcome changed (see workspace **Definition of Done**).

### A.5 Summarize with evidence blocks (mandatory)

Include explicit blocks:

- **Verified** — what you ran and what passed.
- **Not verified** — what was skipped and why.
- **Residual risk** — what could still break in production or for the next contributor.

---

## Part B — Default: finish Pull Request with GitHub CLI

Run **after** Part A unless **Skip Part B** applies. Agents should **attempt** this flow whenever the user runs `/finish-task` without opting out.

### Skip Part B (no merge)

Do **not** run `gh pr merge` when any of the following is true; finish with Part A only, state **why** Part B was skipped, and list manual next steps:

- The user **explicitly** asked to skip merge or PR work (examples: “no merge”, “skip PR”, “verification only”, “solo cierre local”, “do not merge”, “sin fusionar PR”).
- There is **no open PR** for the current branch and the user did not ask to open one.
- `gh` is **missing or not authenticated**; merge would require the GitHub UI instead.
- **CI is failing**, **branch protection** blocks merge, **review is required** but missing, or merge would violate team policy—report the blocker; do not force-merge.
- The user is **already on the default branch** with a clean tree and there is nothing to merge (task was docs-only on `main`, or PR was merged elsewhere).

If the PR was **already merged** in the GitHub UI before Part B, skip `gh pr merge` and run **B.8** only.

### B.1 Verify current state

```bash
git branch --show-current
git status
gh pr status
```

**Expected:** On the feature branch (or the branch linked to the PR), clean working tree, PR open (or draft with a plan to mark ready).

### B.2 Mark PR as ready (if draft)

```bash
gh pr list --head "$(git branch --show-current)"
gh pr ready <PR-number>
```

Skip if already ready.

### B.3 Merge PR (default action)

```bash
gh pr merge <PR-number> --merge --delete-branch
```

Alternatives: `--squash` or `--rebase` per team policy. `--delete-branch` removes the remote branch after merge.

### B.4 Sync local `main`

```bash
git checkout main
git pull origin main
```

If your default branch is not `main`, replace with the repository default.

### B.5 Delete local feature branch

After switching to `main`, remove the old branch (use the actual branch name):

```bash
git branch -d <feature-branch-name>
```

If Git refuses because of a diverged history but the PR is already merged:

```bash
git branch -D <feature-branch-name>
```

### B.6 Prune and verify

```bash
git fetch --prune
git status
git log --oneline -5
```

**Expected:** On `main`, clean tree, up to date with `origin/main`, feature branch gone locally and remote refs pruned.

### B.7 Quick full sequence (reference)

```bash
git status
gh pr status
# gh pr ready <PR-number>   # if draft
gh pr merge <PR-number> --merge --delete-branch
git checkout main
git pull origin main
git branch -d <feature-branch-name>
git fetch --prune
git status
```

### B.8 If the PR was merged in the UI

Skip `gh pr merge`; only sync and cleanup:

```bash
git checkout main
git pull origin main
git branch -d <feature-branch-name>  # or -D if needed
git fetch --prune
```

---

## Common issues (PR path)

| Symptom | What to do |
|--------|------------|
| PR already merged | Sync `main`, delete local branch, `git fetch --prune` |
| Branch “not fully merged” on `git branch -d` | Use `-D` only if you are sure the PR is on `main` |
| Cannot delete branch | `git checkout main` first, then delete |
| `remote ref does not exist` after merge | Normal; run `git fetch --prune` |
| Draft PR | `gh pr ready <n>` then merge |

---

## Task closure checklist

- [ ] No `.env` or real secrets in commits or staged files.
- [ ] `.env.example` updated if settings changed.
- [ ] Tests or smallest meaningful manual checks completed.
- [ ] Canonical work-item (and mirror if used) updated; Second Brain updated when learning or session outcomes require it.
- [ ] Follow-up tasks are explicit.
- [ ] Response includes **Verified / Not verified / Residual risk**.

## PR completion checklist (default; or document skip)

- [ ] Retrospective / canonical doc complete **before** merge (when merge runs).
- [ ] PR approved and CI green per team rules (when merge runs).
- [ ] PR merged (via `gh` or UI); on default branch locally; `git status` clean—or **Skip Part B** documented with reason and follow-ups.
- [ ] Feature branch removed locally after merge; `git fetch --prune` done—or same skip note.

---

## Rules

- Do not mark work complete if the app cannot start and the task required runtime behavior — unless that limitation is documented as accepted residual risk.
- Do not hide failed checks or failed tests.
- If no automated suite exists yet, say so and perform the smallest useful manual verification.
- If requirements or design changed materially during implementation, the canonical document must reflect that before closing.
- Never close a task without the **Verified / Not verified / Residual risk** summary.
- **Default:** after Part A, run Part B (merge + sync + cleanup) when a PR exists and policy allows; only skip when the user opts out or a blocker is documented.

## Related

- `/commit-pending` — stage and commit pending work before PR or handoff.
- `/start-task` — canonical doc paths, Phase 6–7 completion and retrospective discipline.
- `/testing`, `/check-dod`, `/check-quality`, `/check-architecture` — focused gates.
- **Skill:** `validation-pass-fastapi` — optional condensed validation for FastAPI/Python changes.

---

**Last updated:** 2026-05-13  
**Status:** Active
