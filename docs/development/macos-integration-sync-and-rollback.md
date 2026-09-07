# macOS Foreground MVP — Upstream Sync and Rollback Procedure

Status: **required integration workflow**

Applies to: `ok-script` and the companion `ok-wuthering-waves` integration branches

## 1. Principles

- The published long-lived branch is `feature/macos-foreground-mvp` in each contributor fork.
- `origin` is the contributor fork; `upstream` is the canonical `ok-oldking` repository.
- Keep both repositories independent and coordinate them as one delivery unit.
- Prefer preserving published history. Do not force-push the shared integration branch as a routine sync mechanism.
- A sync or rollback may never weaken foreground-only, public-API-only, fail-closed input behavior.
- Any regression reopens its capability gate and invalidates later evidence that depended on it.

## 2. When to sync

Sync both repositories:

- before starting a new implementation stage;
- when upstream changes touch files in the current inventory/change set;
- before real-hardware acceptance;
- before packaged-app acceptance;
- immediately before the final PR freeze.

Do not sync one repository and continue cross-repository validation against an unknown companion state. Record both SHAs used for each acceptance run.

## 3. Pre-sync checks

Run in each repository:

```bash
git status --short --branch
git remote -v
git fetch --prune origin
git fetch --prune upstream
git rev-list --left-right --count HEAD...upstream/master
```

Requirements:

- worktree and submodules are clean;
- current branch is `feature/macos-foreground-mvp`;
- branch tracks `origin/feature/macos-foreground-mvp`;
- remotes have the expected identities;
- no unreviewed generated lock or build artifact is present.

Create a local recovery ref before integrating upstream:

```bash
git branch backup/macos-foreground-pre-sync-YYYYMMDD-HHMM HEAD
```

Record in the relevant acceptance note:

- pre-sync `HEAD`;
- `upstream/master` SHA;
- companion repository SHA;
- backup ref name;
- stage and tests that were green before sync.

## 4. Default sync procedure

Because the integration branch is published and may be shared, the default is a normal merge rather than history rewriting:

```bash
git switch feature/macos-foreground-mvp
git merge --no-edit upstream/master
```

If conflicts occur:

1. do not resolve by discarding platform guards or Windows behavior;
2. compare the upstream intent with the current stage inventory;
3. keep conflict resolution focused on the files actually touched;
4. update the inventory or create an ADR if upstream introduces an architectural conflict;
5. run `git diff --check` before committing the merge.

A rebase is allowed only when the branch has not been shared, or when collaborators explicitly coordinate it. Any rewritten push must use `--force-with-lease`, never plain `--force`. Rebase is not the routine workflow for this long-lived branch.

After syncing `ok-script`, validate the companion editable checkout before syncing OK-WW. Then sync OK-WW and run the cross-repository smoke tests again.

## 5. Post-sync validation

Run the tests applicable to the current stage. At minimum after Stage 2 begins:

```bash
# From the OK-WW checkout
./.venv/bin/python -m pip install -e "../ok-script[ocr,qt]"
./.venv/bin/python -m pip install -e ".[dev]"
./.venv/bin/python -c "import ok"
./.venv/bin/python -c "from ok.device.DeviceManager import DeviceManager"
```

Also run:

- Windows regression CI/tests for changed framework paths;
- Mac import/provider tests;
- stage-specific contract tests;
- task-module import discovery when OK-WW is affected.

For later stages, repeat any hardware or packaged-app checks invalidated by the upstream change. Do not reuse acceptance evidence across a relevant sync without revalidation.

Push only after review and validation:

```bash
git push origin feature/macos-foreground-mvp
```

No incremental PR is opened as part of routine synchronization.

## 6. Rollback before push

### Conflict not committed

```bash
git merge --abort
# or, when an explicitly coordinated rebase was used:
git rebase --abort
```

### Merge/commits created locally but not pushed

After confirming the worktree contains no wanted uncommitted work:

```bash
git reset --hard backup/macos-foreground-pre-sync-YYYYMMDD-HHMM
```

`reset --hard` is allowed only against the recorded local backup ref and only before the changed history is shared.

## 7. Rollback after push or collaboration

Do not rewrite shared history. Revert the offending change:

```bash
# Revert a normal commit
git revert <commit>

# Revert a merge commit, preserving first-parent integration history
git revert -m 1 <merge-commit>
```

Then run the same validation required for the original change and push the revert normally.

For a cross-repository incompatibility:

1. first stop or revert the consumer behavior in OK-WW so it cannot call an incompatible or unsafe framework path;
2. revert or repair the `ok-script` implementation;
3. restore the sibling editable install and test matrix;
4. update the final immutable dependency note;
5. reopen every affected capability gate.

Never keep a mutable branch dependency as a rollback shortcut.

## 8. Safety-critical rollback

If a regression can leak input, leave keys/buttons held, use stale geometry, bypass permission, or post while another app is frontmost:

1. mark the capability unsupported immediately;
2. close the ordinary-input gate in the implementation path;
3. ensure `release_all()` remains reachable and best-effort;
4. revert the unsafe change before continuing feature work;
5. rerun focus-loss, shutdown, target-loss, and permission-loss tests;
6. discard dependent hardware/package acceptance evidence.

A rollback must fail closed. It must not restore a global-input fallback, `CGEvent.postToPid`, private API, virtual display, injection, or TCC workaround.

## 9. Final PR preparation

Before final PR creation:

- sync and validate both repositories at recorded SHAs;
- ensure both worktrees are clean;
- ensure each branch tracks its contributor-fork origin branch;
- record the exact immutable framework revision/version consumed by OK-WW;
- remove development-only local-path assumptions from distributable metadata;
- include migration and rollback notes in both PR descriptions;
- link the companion PRs as one release unit.
