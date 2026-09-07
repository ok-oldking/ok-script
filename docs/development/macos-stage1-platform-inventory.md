# macOS Foreground MVP — Stage 1 `ok-script` Platform Inventory

Status: **complete**

Recorded: 2026-09-04

Scanned branch: `feature/macos-foreground-mvp`

Pre-Stage-1 HEAD: `670ba36e148f954eb353f9c264920a33bf6229a7`

Starting `upstream/master`: `784231e1c5f57a76baf5b4c2ccdef85bbe1d5766`

This inventory maps the current framework blockers to implementation stages. It changes no runtime behavior and does not claim that any macOS runtime capability is implemented.

## 1. Scope confirmation

The following boundary is confirmed for this contributor integration branch:

- the MVP is foreground-only;
- only public Apple APIs are allowed;
- input fails closed when focus, target, permission, capture, geometry, task, or application state becomes invalid;
- reusable platform capability belongs in `ok-script`;
- Wuthering Waves matching, task behavior, assets, and game documentation remain in `ok-wuthering-waves`;
- existing Windows WGC, BitBlt, HWND, interaction, ADB, browser, and public task behavior must be preserved;
- BetterDisplay, virtual displays, `CGEvent.postToPid`, private APIs, injection, hooks, TCC modification, and permission bypasses remain outside the MVP.

No conflict was found between this repository's `AGENTS.md`, `docs/development/macos-foreground-platform-constraints.md`, and the companion OK-WW constraints and plan. This record confirms contributor scope; it does **not** claim prior endorsement by upstream maintainers. Upstream acceptance remains a final-PR gate, and future maintainer feedback that changes architecture must be handled before runtime work continues, using an ADR when the normative boundary would change.

At scan time both source repositories were one Stage 0 documentation commit ahead of, and zero commits behind, their recorded `upstream/master` bases.

## 2. Inventory method

The scan covered:

- `pyproject.toml` and `setup.py`;
- package-level and device-level re-export modules;
- Python files containing Win32 imports, `winreg`, Windows-only third-party input/audio packages, `ctypes.windll`, or `ctypes.WinDLL`;
- Qt, web, notification, overlay, process, Explorer, analytics, emulator, and capture paths;
- existing tests and GitHub workflows;
- the base capture/interaction contracts and `DeviceManager` provider model.

The source scan found:

- 18 Python files with direct top-level imports of Win32 or Windows-oriented input modules;
- 22 Python files with references to Windows DLL access through `ctypes` (with overlap, and with some references already guarded);
- several shared re-export modules that eagerly pull Windows implementations into otherwise platform-neutral imports.

A Windows-only module is not itself a defect. It becomes a Mac blocker when shared code imports it before platform selection or when package metadata installs it unconditionally.

## 3. Packaging and dependency blockers

| ID | Location | Finding | Impact | Assigned work |
|---|---|---|---|---|
| PKG-01 | `setup.py`, `[build-system]` | Editable build requirement evaluation imports `get_pypi_latest_version`, but the isolated build requirements do not provide it. The build also depends on querying published package state when no explicit version is supplied. | Local editable install fails before dependency resolution. Build behavior is not deterministic/offline-safe. | **Stage 2:** make isolated editable/build metadata evaluation deterministic and independent of an undeclared runtime import or network lookup. |
| PKG-02 | `pyproject.toml` core dependencies | `pywin32>=306,!=312` is unconditional. | macOS resolver has no matching distribution, blocking all normal installs. | **Stage 2:** apply a Windows environment marker. |
| PKG-03 | `pyproject.toml` core dependencies | `pydirectinput`, `pycaw`, and `mouse` are unconditional although their consumers are Windows-specific. `comtypes` is pulled transitively by `pycaw`. | Mac installation either fails or installs irrelevant platform dependencies. | **Stage 2:** mark Windows-only dependencies or move them to a Windows-specific extra without changing Windows defaults. |
| PKG-04 | `pyproject.toml`, `interaction_methods/pynput.py`, `RecordScript.py` | `pynput` is unconditional even though it is an optional interaction/recording implementation and is forbidden as the production macOS backend. | Core install and permission surface are wider than the MVP requires. | **Stage 2:** lazy-load and place in an appropriate optional/diagnostic dependency boundary; never select it as the production Mac backend. |
| PKG-05 | `pyproject.toml` `default` extra | `ok-d3dshot` is a Windows desktop duplication dependency. | The advertised default extra is not platform-neutral. | **Stage 2:** add a Windows marker while preserving Windows installation behavior. |
| PKG-06 | `pyproject.toml`, `ok/__init__.py`, `ok/ui/qt/MainWindow.py` | `pyappify` is unconditional and imported on core/Qt startup. Its macOS launcher/update suitability has not been established and current product packaging is Windows-oriented. | Source bring-up can be blocked by a non-core launcher/update path. | **Stage 2:** make imports/platform behavior safe and allow explicit Mac P0 disablement. **Stage 7:** choose the supported `.app` deployment path. |
| PKG-07 | `pyproject.toml` | No macOS PyObjC framework wrappers are declared. | Future AppKit/Quartz/ScreenCaptureKit code would rely on undeclared local state. | **Stage 2:** declare only the minimal wrappers required by later stages, with Darwin markers. |
| PKG-08 | project classifiers | The project advertises only Microsoft Windows. | Metadata would misrepresent support once Mac gates pass. | **Stage 2 or final stabilization:** add a macOS classifier only when the corresponding install/import support is real. |

`pyproject.toml` remains the dependency source of truth. The Stage 2 implementation must regenerate any generated lock output instead of hand-editing it.

## 4. Shared import choke points

These paths must become platform-safe before Mac backends are implemented.

| ID | Import path | Current coupling | Required disposition |
|---|---|---|---|
| IMP-01 | `ok/device/DeviceManager.py` | Top-level imports pull `ok.device.capture`, `ok.device.interaction`, and `ok.util.window`, binding the manager to HWND, WGC/BitBlt, Win32 interactions, and Windows utilities before provider selection. The provider model currently recognizes `windows`, `browser`, and `adb`, not a generic desktop/Mac provider. | **Stage 2:** load providers after config/platform selection and keep Windows construction unchanged behind its provider. **Stage 3:** add the desktop target/Mac provider. |
| IMP-02 | `ok/device/capture.py` and `ok/device/capture_methods/__init__.py` | Wildcard and aggregate exports import BitBlt, WGC, desktop duplication, HWND helpers, and Win32 utility modules unconditionally. | **Stage 2:** separate common exports from platform exports and preserve compatibility through lazy attributes or explicitly platform-scoped imports. |
| IMP-03 | `ok/device/interaction.py`, typo compatibility module `ok/device/intercation.py`, and `ok/device/interaction_methods/__init__.py` | Aggregate exports import PostMessage, Genshin, PyDirect, Pynput, Windows key maps, and related packages before a backend is selected. | **Stage 2:** expose common bases without loading concrete platform implementations; retain legacy import names through lazy compatibility. |
| IMP-04 | `ok/device/interaction_methods/keys.py` | A shared file imports `win32con` at module load while also containing ADB and normalized key data. | **Stage 2:** split platform-neutral/ADB, Windows VK, and later Mac key maps. |
| IMP-05 | `ok/device/capture_methods/types.py` | Shared image enums/helpers import `win32gui` only to implement `is_valid_hwnd`. | **Stage 2:** separate HWND validation from platform-neutral frame types. |
| IMP-06 | `ok/util/window.py` | Top-level `win32api`, `win32con`, `win32gui`, `win32process`, and `ctypes.WinDLL('user32')`; imported by `DeviceManager` and browser capture. | **Stage 2:** make Windows window utilities explicitly Windows-owned and prevent shared imports. **Stage 3:** introduce the common desktop target contract rather than generalizing this module. |
| IMP-07 | `ok/__init__.py` `OK.__init__` | Resolves `windows_graphics_available` even when no Windows config exists, imports `pyappify`, and wires Windows assumptions into generic startup. | **Stage 2:** resolve Windows-only services only for a Windows provider and isolate optional launcher behavior. |
| IMP-08 | `ok/core/start_controller.py` | Imports broad capture exports and Windows process/start-method helpers in shared startup control. | **Stage 2:** depend on platform-neutral capture/device capabilities and a platform start service. |
| IMP-09 | Qt startup chain | `MainWindow` constructs `StartTab`; `StartTab` imports `StartCard` and `DebugTab.capture`; both `StartCard.py` and `DebugTab.py` import `ctypes.windll`/`wintypes` at module scope. `DebugTab` also imports broad capture/interaction exports. | **Stage 2:** make the Qt application importable and startable without Win32. Mac P0 may disable Windows global-hotkey/debug pieces explicitly. |
| IMP-10 | notifications | `ok/notification/__init__.py` imports `NotificationManager` and Windows notifier classes; `NotificationManager` imports `windows_messenger.py` at module scope, which imports multiple Win32 modules. | **Stage 2:** provider-select notification implementations and avoid importing QQ/WeChat desktop automation on Mac. Qt tray or no system notifier is acceptable for P0. |
| IMP-11 | overlay exports | `ok/ui/overlay/__init__.py` exposes only `Win32GdiOverlay`; app facades construct it lazily when overlay is enabled. | **Stage 2:** ensure the overlay capability is explicitly unavailable on Mac without importing/constructing Windows UI. No Mac overlay parity is required for MVP. |
| IMP-12 | browser capture | `capture_methods/browser.py` imports `win32gui`, Windows window helpers, BitBlt utilities, and WGC at module scope. | **Stage 2:** do not import this implementation for the native Mac provider. Browser support is not a substitute for the native Mac MVP. |
| IMP-13 | optional Qt tools | `RecordScript.py` imports `win32gui` and `pynput` at module scope; `OverlayWidget.py` imports `win32api`. | **Stage 2:** keep these optional paths from blocking application/task imports. Mac P0 can mark them unavailable. |

## 5. Windows-only implementations to preserve, not generalize

The following files may remain Windows-specific. Stage 2 should hide them behind dependency and import boundaries rather than rewrite them for visual symmetry.

### Capture and windowing

- `ok/device/capture_methods/bitblt.py`
- `ok/device/capture_methods/bitblt_utils.py`
- `ok/device/capture_methods/desktop_duplication.py`
- `ok/device/capture_methods/hwnd_window.py`
- `ok/device/capture_methods/windows_graphics.py`
- `ok/capture/windows/`
- `ok/util/window.py`
- `ok/util/print_hwnd.py`
- `ok/rotypes/`

### Interaction

- `ok/device/interaction_methods/post_message.py`
- `ok/device/interaction_methods/foreground_post_message.py`
- `ok/device/interaction_methods/genshin.py`
- `ok/device/interaction_methods/pydirect.py`
- the Windows VK map extracted from `keys.py`

### Windows utilities and optional integrations

- `ok/alas/emulator_windows.py`
- `ok/notification/messenger_images.py`
- `ok/notification/windows_messenger.py`
- `ok/ui/overlay/win32_gdi.py`
- `ok/ui/qt/util/windows_thumbnail.py`
- `ok/util/gpu_driver_settings.py`
- `ok/util/windows_schedule.py`

The invariant is: Windows callers retain behavior and public compatibility, while Darwin/shared imports do not load these modules.

## 6. Cross-platform helpers requiring explicit behavior

| Area | Current observation | P0 disposition |
|---|---|---|
| Process/single instance | `ok/util/process.py` combines portable process inspection with Windows mutex, admin elevation, process enumeration, launcher, and prevent-sleep calls. | Split or guard by platform. Mac must not require root; single-instance behavior must be explicit and import-safe. |
| Open/reveal paths | `ok/util/explorer.py` returns false outside Windows and exposes Windows-specific naming. | Add/route through a platform-neutral open/reveal service before OK-WW removes its `os.startfile` calls. |
| Analytics/screen metrics | `ok/util/Analytics.py` obtains screen size through `user32`. | Use a platform-neutral source or omit the field on Mac; analytics must not block startup. |
| Main UI hotkeys | `StartCard.py` registers F9–F12 with `RegisterHotKey`; `DebugTab.py` registers Ctrl+Alt hotkeys with Win32 message polling. | Import-safe explicit disablement is sufficient for Mac P0; Qt-native shortcuts may be evaluated separately. |
| System tray/notifications | Qt tray may be portable, but the headless native notifier and desktop QQ/WeChat automation are Windows-specific. | Select a portable/Qt notifier or `None`; do not port Windows desktop messenger automation for MVP. |
| Launcher/updater | PyAppify is wired into startup, update checks, shutdown, and a Windows zip config. | Do not block source mode. Disable or isolate for Mac until Stage 7 packaging decides the supported path. |
| Browser provider | Current browser capture is built around Windows browser HWND/WGC. | Keep Windows behavior; native Mac MVP does not require browser-provider parity. |
| Overlay and thumbnail tools | GDI overlay is Windows-only; Windows Shell thumbnails already have a platform guard. | Overlay disabled on Mac P0. Keep thumbnail fallback behavior without adding Mac parity. |
| Audio/HDR/Night Light/GPU controls | Audio mute is coupled to HWND/pycaw; driver/display controls are Windows-oriented. | Explicitly unavailable on Mac P0 and never allowed to block capture/input. |

## 7. Platform contract gaps assigned to later stages

| Contract gap | Current state | Stage |
|---|---|---|
| Platform-neutral desktop target and Windows adapter | Absent; HWND is the desktop model. | **Stage 3** |
| Mac app/window discovery, identity, observed activation, rebind | Absent. | **Stage 3** |
| Permission service | Absent. | Service shape in **Stage 3**; capture permission integration in **Stage 4**; Accessibility integration in **Stage 5**. |
| Persistent ScreenCaptureKit stream and latest-frame ownership | Absent. | **Stage 4** |
| Geometry generation and frame-pixel conversion contract | Absent as a shared cross-platform contract. | **Stages 3–4** |
| Quartz key/mouse backend and Mac key map | Absent. | **Stage 5** |
| Held-key/button state and fail-closed input gate | `BaseInteraction.send_key_down`, `send_key_up`, and `on_destroy` are no-op defaults; no base `release_all()` contract exists. | **Stage 5** |
| Cursor service | Absent. | **Stage 5**, then consumed by OK-WW in **Stage 6**. |
| Mac provider in `DeviceManager` | Absent. | Import boundary in **Stage 2**, provider/target integration in **Stage 3**. |

## 8. Existing tests and CI gaps

Current useful regression tests include DeviceManager, capture update, Windows graphics capture, process/mutex, Explorer, startup controller, runtime startup, notifications, overlay, and base interaction tests. They are valuable Windows behavior anchors.

Known gaps and portability blockers:

- `tests/test_notifications.py` imports `win32con` and the Windows messenger implementation at module scope;
- `tests/test_windows_graphics_capture.py` imports HWND/WGC implementations at module scope;
- current `tests/test_base_interaction.py` covers logging throttling, not held state, release, focus, or shutdown safety;
- no tests cover Darwin provider selection, no-Win32 import isolation, desktop target contracts, geometry generations, ScreenCaptureKit buffer conversion/ownership, permission states, or Quartz event gating;
- the repository currently has a publish workflow but no general cross-platform test workflow.

Disposition:

- **Stage 2:** add deterministic import/provider tests and make Windows-only tests explicitly Windows-scoped instead of failing during Mac collection;
- **Stages 3–5:** add contract tests with fake platform adapters/event sinks;
- **Stage 7:** add macOS Python 3.12 CI and retain/establish Windows CI without requiring the game.

## 9. Stage 2 minimum change boundary

Stage 2 is complete only when it can satisfy all of the following without implementing production Mac capture/input:

1. PEP 517/editable metadata evaluation succeeds deterministically;
2. normal Mac dependency resolution selects no Windows-only packages;
3. `import ok`, `DeviceManager`, core executor/startup modules, shared capture/interaction bases, Qt application modules, and OK-WW task discovery import without Win32 modules;
4. Windows providers still select the existing implementations and existing Windows tests remain green;
5. Mac-specific concrete modules may be placeholders only where a provider is not yet selected, but must not report capture/input success;
6. optional Windows-only UI/tools are explicitly unavailable rather than silently swallowed;
7. no ScreenCaptureKit, Quartz event posting, game matching, or task compatibility implementation is smuggled into Stage 2.

## 10. Stage 1 exit assessment

- [x] Normative scope and forbidden mechanisms compared; no unresolved internal rule conflict found.
- [x] Packaging and dependency blockers mapped to Stage 2.
- [x] Shared import choke points mapped to Stage 2.
- [x] Windows-only implementations identified for preservation behind lazy platform boundaries.
- [x] Later desktop target, capture, input, permission, cursor, geometry, test, and packaging work mapped to Stages 3–7.
- [x] Existing test and CI gaps recorded.
- [x] No runtime code changed by this inventory.

The framework inventory is sufficient to begin Stage 2 without expanding the product scope.
