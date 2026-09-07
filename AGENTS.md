# AI Coding Instructions

## macOS Foreground Port Scope

This repository owns the reusable platform layer for the OK-WW **macOS foreground-only** MVP.

Before changing macOS-related platform code, read:

- `docs/development/macos-foreground-platform-constraints.md`
- `docs/development/macos-stage1-platform-inventory.md`
- `docs/development/macos-integration-sync-and-rollback.md`
- `docs/development/decisions/README.md`
- the companion OK-WW `MACOS_ENGINEERING_CONSTRAINTS.md`
- the companion implementation plan at `docs/development/macos-foreground-port-plan.md`
- applicable repository skills under `.agents/skills/`

The framework implementation must not expand the product into background control, private APIs, process injection, or permission bypasses.

框架公开 API 设计与通用 host gate 保留 Apple Silicon、macOS 13+；当前 OK-WW packaged MVP 因 Python/PySide6 原生依赖收窄为 macOS 15+，见 `docs/development/decisions/0002-consumer-packaged-minimum-version.md`。consumer 发行基线不应反向提高通用 host gate，也不得据此声称框架依赖组合已在 macOS 13/14 完整验收。此为用户授权的 contributor 分支决定，upstream 接受仍待最终审查。

## Instruction Precedence and Change Control

- The companion OK-WW `MACOS_ENGINEERING_CONSTRAINTS.md` is the normative product contract.
- `docs/development/macos-foreground-platform-constraints.md` is normative for reusable platform implementation in this repository.
- More specific repository instructions may tighten implementation details but must not relax foreground-only operation, public-API-only operation, fail-closed input safety, or Windows compatibility.
- Any deliberate deviation requires a committed architecture decision record before implementation proceeds. It must describe alternatives, security and permission impact, Windows regression impact, tests, migration, and rollback.

## Branch and Repository Policy

- Develop on the long-lived `feature/macos-foreground-mvp` integration branch created from recorded `upstream/master`.
- `origin` is the contributor fork; `upstream` is `ok-oldking/ok-script`.
- Keep the companion OK-WW checkout on the matching integration branch.
- Use the sibling checkout through editable installation during development; do not publish temporary packages or vendor this repository into OK-WW.
- Keep commits logically scoped and bisectable, but do not open incremental or foundation-only PRs.
- Do not push runtime work to a default branch or open the final MVP PR until the applicable acceptance gates pass.
- The final OK-WW dependency must reference an immutable accepted `ok-script` version or commit, never a mutable branch URL.
- Never commit credentials, signing identities, notarization material, TCC data, personal screenshots, private logs, `.venv`, `.app`, `.dmg`, or generated build output.

## Python Environment

When running Python commands, prefer the repository virtual environment if it exists.

- Windows/PowerShell: `.\.venv\Scripts\python.exe`
- macOS/POSIX: `./.venv/bin/python`
- Fall back to `python` only when no repository-local interpreter exists.
- Invoke the interpreter directly for package tooling, tests, compilation, and scripts.
- The OK-WW macOS reference interpreter is Python 3.12 arm64.

## Repository Ownership Boundary

Reusable platform capability belongs here:

- platform-neutral device routing
- desktop window-target abstractions
- Windows adapters preserving existing behavior
- macOS application and window discovery
- ScreenCaptureKit capture
- Quartz foreground keyboard and mouse input
- foreground/focus guard
- held key/button state and `release_all()`
- `DeviceCapabilities` and generic task capability gates
- cursor service
- permission service
- coordinate conversion
- platform-conditioned dependencies and imports
- capture/input lifecycle and failure states

Game-specific configuration and behavior belong in `ok-wuthering-waves`:

- Wuthering Waves app/window matching hints
- verified bundle identifiers
- game hotkey choices
- task compatibility decisions
- game-specific asset overrides
- OK-WW user documentation

Do not add Wuthering Waves-specific matching, task logic, or assets to this framework merely to make the first consumer work.

## Platform Dependency and Import Rules

Platform-neutral modules must import on Windows and macOS.

- No unconditional `win32api`, `win32con`, `win32gui`, `win32process`, `winreg`, `ctypes.windll`, or `ctypes.WinDLL` imports in shared modules.
- No unconditional AppKit, Quartz, ScreenCaptureKit, ApplicationServices, or PyObjC imports in shared modules.
- Put implementations in platform-specific modules and load them only after platform selection.
- Use environment markers in `pyproject.toml` for platform-specific dependencies.
- Keep `pyproject.toml` authoritative; regenerate lock files rather than hand-editing generated output.
- Do not scatter broad `try/except ImportError` blocks through shared code to hide an incorrect dependency boundary.
- macOS import smoke must cover `import ok`, `DeviceManager`, task executor, device abstractions, and test discovery without loading Win32-only modules.
- Windows import and test paths must not require PyObjC.

## Desktop Target and Coordinate Contract

- Introduce a platform-neutral desktop window target; do not turn `HwndWindow` into a nominally generic type full of HWND assumptions.
- Windows should adapt existing HWND behavior with minimal regression risk.
- macOS may bind `NSRunningApplication`, `SCWindow`, `CGWindowID`, PID, and bundle identifier behind the common contract.
- Capture and task coordinates are frame-local physical pixels.
- Only platform backends convert frame coordinates to logical points or global screen coordinates.
- Every frame/input operation must use a current geometry generation; stale frames and stale coordinates are invalid after resize, rebind, scale change, or capture failure.
- Retina conversion tests must not assume a fixed 2.0 scale.

## ScreenCaptureKit Contract

- Use a persistent `SCStream` for continuous automation capture.
- Prefer `SCContentFilter(desktopIndependentWindow:)` for the selected window.
- `SCScreenshotManager`, whole-display capture, and desktop crop are diagnostic-only and must never become production fallback paths.
- Publish only the newest complete frame through bounded storage.
- Do not run OCR, recognition, task logic, or Qt updates in the ScreenCaptureKit callback.
- Output must be owned/stable BGR `numpy.ndarray`, `uint8`, shape `(height, width, 3)`, content-only, without cursor, title bar, shadow, or border.
- Detect window recreation, process exit, resize, display-scale changes, permission revocation, and stream failure. Recover with bounded backoff or enter an explicit terminal state.
- Old frames and geometry become invalid as soon as rebind or geometry change starts.

## Quartz Foreground Input and Safety Contract

- Production macOS input uses public Core Graphics Quartz events.
- `pynput` may be an isolated diagnostic only, not the architectural backend.
- Support independent key down/up, left/right/middle mouse down/up, absolute movement, and a separately declared relative/delta capability.
- Immediately before every event or short atomic batch, verify the target exists, is alive, and is the system frontmost application.
- Never send first and check focus afterward.
- Do not use `CGEvent.postToPid` as a hidden background fallback.
- Track all synthetic held keys and buttons explicitly.
- `release_all()` must be idempotent, safe after target disappearance, best-effort across individual failures, and clear internal state even when posting release events fails.
- Ordinary input, focus invalidation, shutdown, and `release_all()` must share a thread-safe gate. Once invalidated, no new ordinary input may cross it.
- On focus loss, only releases corresponding to tracked held state may be posted; do not generate movement, clicks, scrolling, text, or new down events.
- Shutdown order is: block new input, call `release_all()`, stop capture/workers, then destroy Qt/Python objects.
- Relative camera movement remains `not-implemented` or `unit-tested` until validated in the official game on real hardware.
- Do not make `relative_mouse` a global release blocker. A consumer may ship hardware-validated basic or locked-gameplay tasks that do not require free-camera delta.
- Only tasks that explicitly require `relative_mouse` are blocked by that missing capability. Free-camera routes and complete camera parity may not be claimed before the corresponding gate passes.

## Capability Model

`ok-script` owns a platform-neutral, fail-closed `DeviceCapabilities` model. At minimum it distinguishes keyboard tap, keyboard hold, absolute mouse, left/right/middle buttons, button hold, scroll, relative mouse, and foreground-only guarantees.

- All new providers default every capability to false until explicitly declared.
- Task requirements are checked before enablement and immediately before execution.
- An inherited empty method never implies a capability is available.
- Game-specific levels such as `MAC_BASIC`, `MAC_LOCKED_GAMEPLAY`, and `MAC_FULL_CAMERA` belong in the consumer repository; the framework only exposes precise capabilities and generic matching.
- Provider capability evidence and consumer task support status are separate axes.

## Permissions

- Use supported screen-capture and Accessibility preflight/request APIs.
- Missing permission is an explicit actionable state, not a retry loop.
- Never modify TCC databases, request root to bypass permission, or claim Terminal/Python permission proves packaged-app permission.
- Packaged-app acceptance must use a stable bundle identifier. Establish an internal stable-identity `.app` early enough to test TCC behavior after the window/permission boundary exists; do not postpone permission identity until all tasks are complete.

## Testing and Windows Regression

Every platform-layer change must preserve:

- WGC and BitBlt behavior
- current Windows interaction methods
- HWND selection behavior
- public task APIs and configuration keys
- current ADB behavior

Required tests include:

- platform selection and import isolation
- desktop target contracts
- BGRA/BGR frame conversion, stride, ownership, and geometry generation
- coordinate conversion for multiple scale factors
- held input state and idempotent release
- focus loss preventing further input
- shutdown and fatal capture paths calling `release_all()`

CI must not require the game to be installed. Real-game results must be recorded separately from automated tests.

## MaaEnd / MaaFramework Reference Boundary

MaaEnd/MaaFramework may be studied as evidence that ScreenCaptureKit plus Quartz CGEvent is viable. Do not add MaaFramework as an MVP runtime dependency, copy its one-shot screenshot loop, use `SCWindow.frame` as content pixel size, reactivate the target before every event, or infer background support from its background controller. A future runtime dependency requires its own ADR.

## Documentation Language

New or modified macOS engineering constraints, implementation plans, and acceptance records use Chinese by default. Keep API names, class names, function names, paths, configuration keys, log state codes, and commands in English.

## Capability Claims

Use only these evidence states:

1. `not-implemented`
2. `unit-tested`
3. `hardware-validated`
4. `packaged-app-validated`

Do not describe a capability at a higher state than the evidence demonstrates. Later regressions reopen the corresponding gate.
