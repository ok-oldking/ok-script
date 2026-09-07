# macOS Foreground Framework — Stage 0 Bootstrap Record

Status: **complete**

Recorded: 2026-09-04

Integration branch: `feature/macos-foreground-mvp`

## Repository identity

| Item | Value |
|---|---|
| `origin` | `https://github.com/Silhouette-my/ok-script.git` |
| `upstream` | `https://github.com/ok-oldking/ok-script.git` |
| Starting `upstream/master` SHA | `784231e1c5f57a76baf5b4c2ccdef85bbe1d5766` |
| Companion repository | `ok-wuthering-waves` on its matching integration branch |
| Reference host | Apple Silicon, macOS 15.7.9 |
| Reference Python | 3.12.14 arm64 |

The cross-repository command results and full bootstrap checklist are recorded in the companion OK-WW file `docs/development/acceptance/macos-stage0-bootstrap.md`.

## Baseline blockers assigned to Stage 2

1. Editable build requirement evaluation fails because `setup.py` imports `get_pypi_latest_version`, while the isolated `[build-system].requires` list does not include it.
2. The published framework dependency graph requires `pywin32` unconditionally, so OK-WW resolution fails on macOS.
3. Shared imports have not yet been proven free of Win32-only modules.

These failures are intentionally recorded without `--no-deps`, temporary wheels, mutable branch URLs, broad import exception handling, or global-environment workarounds.

## Stage 0 guardrails installed

- framework ownership and game-repository boundary;
- long-lived integration branch and final-PR-only policy;
- platform dependency/import isolation rules;
- persistent ScreenCaptureKit frame contract;
- Quartz foreground guard and held-state release contract;
- coordinate-generation, permission, shutdown, testing and Windows-regression requirements;
- ignore coverage for local environments, macOS build products, signing/notarization material, TCC material and private acceptance evidence.

No ScreenCaptureKit, Quartz input, window discovery, task integration, CI or packaging runtime implementation is part of this commit.

## Exit checklist

- [x] Writable contributor fork and canonical upstream are configured.
- [x] Integration branch starts from the recorded upstream SHA.
- [x] Repository instructions and relevant skills were inspected.
- [x] The canonical framework constraints are present at `docs/development/macos-foreground-platform-constraints.md` on the actual integration branch.
- [x] Cross-repository reference environment and baseline failures are recorded.
- [x] Ignore rules are hardened.
- [x] Bootstrap commit is pushed to the contributor fork.
- [x] No stage PR is opened.
- [x] Worktree is clean after the bootstrap commit.

Stage 0 is complete; the next framework work is the Stage 1 inventory followed by Stage 2 packaging/import isolation.
