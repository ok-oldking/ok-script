---
name: review-pr
description: >-
  Review open GitHub pull requests against master, recommend which PRs to merge,
  close outdated or unsuitable PRs with localized comments signed with the AI
  model name, and cleanly merge approved PRs (including Qt i18n conflict
  resolution and test verification). Use when the user asks to review, triage,
  clean up, or merge open PRs.
---

# Review and Triage Pull Requests

Maintainer workflow for reviewing open GitHub PRs, closing outdated or
unsuitable PRs, and merging recommended ones.

> Note: This skill lives under `.agent/skills/` (not `.agents/skills/`) so it is
> discovered by Antigravity for repository maintenance without being bundled as
> a consumer skill or exposed through MCP.

## 1. Inventory Open PRs and Repo State

Fetch all open PRs and check local branch status in one pass:

```powershell
gh pr list --state open --json number,title,author,createdAt,updatedAt,headRefName,baseRefName,isDraft,mergeable,mergeStateStatus,url --limit 50
git status -sb
git log -n 15 --oneline
```

Then inspect metadata, changed files, comments, and reviews for each PR:

```powershell
gh pr view <number> --json number,title,author,isDraft,mergeable,additions,deletions,changedFiles,commits,comments,reviews,files
```

For large diffs, skip generated translation/resource files (`*.ts`, `*.qm`,
`ok/ui/qt/resources.py`) while reviewing the actual code changes.

## 2. Evaluate Each PR Against Current `master`

Check every PR against the current codebase (not just its diff in isolation):

1. **Outdated / broken target files**: Verify whether modified files still exist
   on `master` (e.g., old `qfluentwidgets` / `ok/gui/tasks/` / `ok/ui/qt/start/`
   files removed in the Qt UI rewrite).
2. **Framework vs. app-specific scope**: For generic framework repos like
   `ok-script`, reject hardcoded game-specific data, UI overlays, or env vars
   (e.g., game-specific UID masks enabled by default, game-specific tables, or
   `OK_WW_*` env vars).
3. **External dependencies & API boundaries**: Verify any referenced upstream
   PRs (e.g., `gh pr view <n> --repo <owner/repo>`) are merged, and reject
   workarounds that bypass public APIs (such as mutating external `app.json`
   directly).
4. **Conflict type**: Distinguish real architectural conflicts from trivial
   drift in shared config (`GlobalConfig.py`) or generated i18n/resource files.
   A clean feature PR that only conflicts on i18n/config is **Merge after
   rebase**, not outdated.
5. **Drafts, staleness, and scope**: Flag inactive Draft PRs, monolithic PRs
   bundling dev-process docs/CI clutter, or fragile tests (e.g., `ast.parse` +
   `exec` instead of testing real classes).

Classify each PR into one of four buckets:
- **Ready to merge**: Clean, focused, mergeable now.
- **Merge after rebase**: Good implementation; only needs conflict resolution
  (e.g., `GlobalConfig.py`, imports, or i18n regeneration).
- **Needs revision (keep open)**: Recent PR with useful direction that needs
  targeted cleanup before merging.
- **Close (outdated / unsuitable)**: Outdated against `master`, stale draft,
  wrong layer/game-specific, or blocked on unmerged external work.

## 3. Close Outdated or Unsuitable PRs

For each PR to close:
1. Write a polite, specific comment explaining **why** it is being closed and
   what to do if the author wants to resubmit.
2. **Match the submitter's language** (check the PR title/body; e.g., Chinese
   for Chinese PRs, English for English PRs).
3. **Sign the comment with this AI's human-readable model name** (do not omit
   the model name):
   - Chinese:
     ```markdown
     ---
     *由 AI 审核（<Human-Readable Model Name>）*
     ```
   - English:
     ```markdown
     ---
     *Reviewed by AI (<Human-Readable Model Name>)*
     ```
4. **Preserve UTF-8 on Windows PowerShell**: Set UTF-8 console encoding before
   calling `gh pr close` (or pass JSON via a UTF-8 file to `gh api`) so
   non-ASCII comments are never garbled:
   ```powershell
   [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
   [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
   $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
   gh pr close <number> --comment $comment
   ```
   Spot-check at least one posted non-ASCII comment via `gh api` to confirm
   clean encoding.

## 4. Report Review Summary

Present a concise Markdown summary grouped by:
- **Recommended to Merge** (ready now vs. merge after rebase)
- **Needs Revision (Kept Open)**
- **Closed PRs** (with author, language, and reason)

Wait for user confirmation before merging unless the user explicitly asked to
merge immediately.

## 5. Merge Recommended PRs (When Requested)

1. **Preserve unpushed local commits**: If local `master` is ahead of
   `origin/master`, do **not** merge directly on local `master`. Create a
   temporary branch from `origin/master` (`git checkout -b merge-recommended origin/master`),
   push `merge-recommended:master`, and then rebase local `master` onto
   `origin/master` afterward.
2. **Clean PRs**: Merge via `gh pr merge <number> --squash` and `git fetch origin master`.
3. **Conflicting PRs (merge commit preserves GitHub "Merged" status)**:
   - Fetch the PR ref: `git fetch origin pull/<number>/head:pr-<number>`
   - Merge without committing: `git merge --no-ff --no-commit pr-<number>`
   - Resolve code conflicts carefully.
   - For Qt `.ts` conflicts, restore `HEAD`'s `.ts`/`.qm`/`resources.py` and
     inject only the PR's newly added `<message>` entries using
     [merge_ts.py](./scripts/merge_ts.py):
     ```powershell
     $py = if (Test-Path .\.venv\Scripts\python.exe) { ".\.venv\Scripts\python.exe" } else { "python" }
     git checkout HEAD -- ok/ui/qt/i18n/ ok/ui/qt/resources.py
     & $py .\.agent\skills\review-pr\scripts\merge_ts.py pr-<number>
     ```
     Never run `pyside6-lupdate` (it deletes existing translations).
   - Recompile `.qm` files and `ok/ui/qt/resources.py` following
     `docs/maintainers/translations.md` using `.venv-qt-tools` and verify
     `0 unfinished` translations.
   - Commit with `Merge pull request #<number> from <owner>/<branch>`.
4. **Run tests before pushing**:
   - Run `pytest` with the repository `.venv` on all affected test suites (clear
     `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` when running loopback HTTP tests
     like `tests/test_mcp_server.py`).
   - If a merged PR intentionally changed behavior that broke an existing test,
     update the test in a follow-up commit and re-verify before pushing.
5. **Push and clean up**:
   - `git push origin merge-recommended:master`
   - Rebase local `master` onto `origin/master`, delete temporary branches
     (`merge-recommended`, `pr-*`), and verify `gh pr list --state open`.
6. **Release (if requested)**: Follow `docs/maintainers/release.md` to tag,
   push, and verify the GitHub Actions release workflow.
