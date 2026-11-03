# PySide6 UI Redesign Plan (drop PyQt-Fluent-Widgets)

Status: proposal. Inspected against `ok-wuthering-waves/main_debug.py` (debug build, dark theme, 1877×1400).

## 1. What the current UI gets wrong

Observed by screenshotting each page of the running app:

| Area | Problem |
| --- | --- |
| Global state | Nothing tells you *at a glance* whether the game window is connected, which task is running, or how to stop it. Status lives in a floating `StateToolTip`; "Start game (F11)" sits only on the Capture page. |
| Navigation | 17 flat items, no grouping. Developer pages (Script, Plugins, Debug, Run Code) are mixed with user pages. Title bar text shows the *last-created* tab name ("开发工具") instead of the current page. |
| Capture page | Three tall list panels with one or three rows each — ~70% empty space. Option text is truncated (`WGC - 速度快，支持 HDR（不支持…`). The disconnected state (`已断开`) is plain text inside a list row. |
| Tasks page | A wall of identical rows, each with its own pink "Start" button (13 primary buttons on one screen = no primary). Config expands inline, pushing everything down; only one task can be viewed at a time and there is no run history or status per task. Rows without settings lose the chevron, so Start buttons don't align. |
| Triggers | Separate page with the same row pattern; on/off is the only state shown. |
| Settings | One long scroll; label/control rows are inconsistent (switches with "是/否" text labels, dropdowns of varying widths, descriptions wrapping at ~320px). |
| About | Update error rendered as wrapped red text in a narrow column; disclaimer is three lines of saturated red. |
| Dev pages | Raw button strips with no hierarchy; empty states are blank (Schedule shows two buttons and a void). |
| Theming | Accent comes from the Windows accent (pink here) and is applied to every primary button, switch and selection, so it dominates. |

## 2. Design direction

Principles taken from current desktop design practice (Windows 11 / Fluent 2, macOS, Linear/Raycast-style tools):

1. **State first, one executor control.** A persistent *Run bar* directly under the title bar (fused with it into one toolbar, so it is the first thing seen), on every page, owns the executor (the `StartController` / `TaskExecutor` session):
   - Left: connection pill (status dot, game name, resolution, capture and interaction method). Clicking it opens the **Connection popover**, which replaces the old Capture tab: window picker, refresh, screenshot, live preview, capture method, interaction method, export logs, folders, OCR test. It has no launch button.
   - Right: the executor button with the **F11** hotkey. F11 belongs to the executor only, never to a task.
     - Stopped → **Start**: launches the game if it is not running (`start_device`), waits until it can be captured, enables `enable_after_start` tasks, starts triggers and queued tasks. This replaces both "Start game" and "Start".
     - Starting → progress ("Launching game · waiting for window · 0:18") and **Cancel**.
     - Running → current task, step, progress, elapsed time, cancel-task ×, queue count, and **Pause**.
     - Paused or blocked (window minimized, disconnected) → reason in red and **Resume**.
2. **Running a task is a separate, explicit action.** A task's **Run task** button (detail header) and each row's ▶ call `start_controller.start(task)`: the task is enqueued and the executor starts if it is stopped, so a single click is enough even when the game is closed. There is no "Start game" step for the user to remember.
3. **One primary action per view.** Exactly one accent button per screen; everything else is secondary/subtle.
4. **Master–detail with one-click run.** Tasks become a list (left) + detail pane (right). Every list row has its own play button, so running a task never needs a select-then-run double click; clicking the row only opens its settings. The list is split into collapsible sections (On-demand, Triggers) that scroll independently. Triggers have inline switches.
5. **Kind tabs plus group tabs.** The tabs above the list always start with `All`, `On-demand` (every one-time task) and `Triggers` (every trigger task), each with a count. After a divider come the group tabs from each task's existing `group_name` / `group_icon` (the categories that today become separate sidebar tabs), with the group icon and a count; they appear only when the app defines groups. The On-demand and Triggers sections in the list always contain every task of their kind that matches the selected tab and scroll instead of truncating. There is no free-text search, here or anywhere else in the app.
6. **Wide config area.** The detail header has only the name, description and actions (no task icon). The settings form gets the pane's full width; last-run results are a one-line summary under the title, with History and Log as tabs instead of a side column.
7. **Grouped, quiet navigation.** Sections: *Run* (Tasks, Schedule), *Game* (app-provided config tabs), *Develop* (debug only), *App* (Settings, About). No Capture/Home page; Tasks is the start page. Collapses to an icon rail. Window title shows the current page.
8. **App-provided icons.** Tasks, task groups and custom tabs take an optional `icon` that is a path to an SVG or PNG in the app (`icons/daily.svg`). SVGs are rendered crisp at any DPI; PNGs are scaled. Without one, the row shows a neutral monogram tile. The framework's own chrome uses a small bundled SVG set (no Fluent icons).
9. **Neutral surfaces, restrained accent.** Graphite/white surface ramp with 3 elevation levels, 1px hairline borders, 8px radius, accent used for focus, selection and the single primary action. Accent still follows the system accent but is desaturated for surfaces.
10. **One window size.** The default window is 1560×820 and the minimum equals the default, so the layout always looks the same; it fits a 1600×900 screen with a taskbar. Saved or app-configured sizes are clamped to the screen's available area.
11. **Density and alignment.** 4px grid, 36px control height, fixed right-aligned control column (240px) in settings rows, descriptions max 60ch.
12. **Feedback where you look.** Toasts bottom-right; empty states with a one-line explanation and an action; inline validation.
13. **Keyboard.** `F11` (configurable) starts, pauses and resumes the executor only.

A visual example is on the design canvas (Tasks, Connection popover, run bar states, Settings light theme).

## 3. Architecture

### 3.1 New internal widget kit: `ok/ui/qt/kit/`

Pure PySide6, no third-party UI dependency, and limited to QtCore, QtGui, QtWidgets and QtSvg. The `qt` extra installs **ok-pyside-minimal**, a repackaged PySide6-Essentials wheel that ships only those modules (no Qt tools, QtTest, QtNetwork, ...). `tests/test_kit.py` checks that neither `ok/` nor `tests/` imports anything else; tests use `tests/qt_helpers.py` instead of QtTest.

Run `python -m ok.ui.qt.kit.gallery [light|dark]` to see every widget.

| Module | Replaces (qfluentwidgets) | Notes |
| --- | --- | --- |
| `theme.py` | `qconfig`, `Theme`, `setTheme`, `isDarkTheme`, `StyleSheetBase`, `setCustomStyleSheet` | Token dict (light/dark) → one generated app-wide QSS; `theme_changed` signal; system accent via existing `_get_dwm_accent_color`. |
| `icons.py` | `FluentIcon`, `FluentIconBase` | Small bundled stroke-SVG set for the framework chrome, tinted to the theme through `QSvgRenderer`. `load_icon(path)` loads an app SVG/PNG (cached per size and DPR; SVGs keep their own colors). |
| `buttons.py` | `PushButton`, `PrimaryPushButton`, `ToolButton` | Variants: primary / secondary / subtle / danger; optional icon. |
| `inputs.py` | `ComboBox`, `SpinBox`, `DoubleSpinBox`, `CompactSpinBox`, `LineEdit`, `SearchLineEdit`, `TextEdit`, `PlainTextEdit`, `CheckBox`, `RadioButton` | Mostly stock Qt widgets + QSS; custom popup for ComboBox. |
| `switch.py` | `SwitchButton` | Painted `QAbstractButton` with `QVariantAnimation`. |
| `cards.py` | `SettingCard`, `ExpandSettingCard`, `SettingCardGroup`, `OptionsSettingCard`, `ComboBoxSettingCard` | `SettingRow` (label, description, control column) + `Section`. |
| `layout.py` | `FlowLayout`, `ExpandLayout` | Port of Qt's FlowLayout example. |
| `navigation.py` | `FluentWindow` navigation, `NavigationItemPosition` | Grouped sidebar + icon-rail mode; keeps a `NavigationItemPosition`-compatible enum (`TOP`, `SCROLL`, `BOTTOM`). |
| `window.py` | `FramelessWindow`, `SplitTitleBar`, `BackgroundAnimationWidget` | Frameless window with native snap via `WM_NCHITTEST`/`WM_NCCALCSIZE`, Mica via `DwmSetWindowAttribute`; falls back to a native frame off Windows. |
| `feedback.py` | `InfoBar`, `StateToolTip`, `IndeterminateProgressRing` | Toast stack, progress ring. |
| `dialogs.py` | `MessageBox`, `MessageBoxBase`, `Dialog`, `MaskDialogBase` | In-window overlay modal with scrim; same `exec()` / `yesButton` API shape to keep call sites small. |
| `table.py` | `TableWidget`, `ListWidget`, `ScrollArea` | QSS + overlay scrollbar. |
| `labels.py` | `BodyLabel`, `StrongBodyLabel`, `CaptionLabel`, `SubtitleLabel`, `TitleLabel` | `QLabel` with a `role` property selected by QSS. |
| `config.py` | `QConfig`, `ConfigItem`, validators, serializers | Small JSON config with signals in a new file; the old `ui_config.json` is not read (theme and language fall back to defaults once). |
| `i18n` | `FluentTranslator` | Kit strings (OK/Cancel/…) go into ok-script's own `.ts` files. |

### 3.2 New shell

- `MainWindow` (no longer a `FluentWindow`): title bar · sidebar · `QStackedWidget` · run bar.
- `RunBar` replaces `StatusBar` + `StateToolTip` and reads the existing executor signals (`executor_paused`, task start/stop, capture error).
- `ConnectionPopover` (opened from the run bar) replaces `StartTab`, `StartCard`, `SelectCaptureListView` and `SelectInteractionListView`. It opens automatically on first launch and when the game window is lost.
- The executor button and global hotkey move from `StartCard` into `RunBar`; the "Start Game" label disappears because launching is a step of Start. `StartController` gains a cancel for the launch wait.

### 3.3 Page redesigns

| Page | Change |
| --- | --- |
| Capture | **Removed**; moved into the run bar's connection popover. Developer tools from its bottom strip move to the Debug page. |
| OneTime + Trigger + group tabs → **Tasks** | `TaskListModel` + `QListView` with delegate (icon, name, description, status pill, row play button or trigger switch); group tabs from `group_name` / `group_icon` replace the per-group sidebar entries; collapsible On-demand and Triggers sections, each scrolling on its own; detail pane builds a full-width form from the same `config_type` metadata the `LabelAndX` widgets use today, grouped by an optional `config_group`. |
| Schedule | Table with empty state; create/edit in a side sheet instead of a modal. |
| Settings | Sections with anchor list on the left, `SettingRow` everywhere. |
| About | Header, update row with clear status chip, disclaimer as a neutral notice, project grid. |
| Debug / Run Code / Script / Templates / Markup / Plugins / Logs | Same features in the kit; logs become a dockable bottom panel. |

### 3.4 Consuming apps (breaking change, no compatibility layer)

- `ok.ui.qt.kit` is the public widget API for custom tabs (`CustomTab`, plugin tabs).
- `icon` on tasks, groups and custom tabs is an SVG/PNG path; `ok.core.icons.Icon` and Fluent icon values are removed.
- `CustomTab.position` becomes a kit enum; no qfluentwidgets aliases, shims or deprecation warnings.
- Apps that import `qfluentwidgets` break and must be ported. ok-wuthering-waves (`CharacterCodeTab`, `MultiAccountConfigTab`) is migrated later as separate work, after this redesign lands.

## 4. Phases

Each phase leaves the app runnable and is verified by launching `ok-wuthering-waves/main_debug.py`, screenshotting pages, and running `pytest`.

1. **Kit foundation** – theme tokens, QSS generator, icons, labels, buttons, inputs, switch, setting rows, dialogs, toasts; a debug-only *Gallery* page with every widget in light/dark. Offscreen pytest-qt tests.
2. **Shell** – new window, title bar, navigation, run bar with executor control and connection popover (Capture tab removed); old pages hosted unchanged inside it (qfluentwidgets still installed).
3. **Tasks** – master–detail Tasks page with row play buttons, sections and app icons; kit config editors (`tasks/config_editors.py`) and `ConfigForm` reuse `ConfigContentMixin`'s sub-config rules. Done; still on the old widgets: the Settings page and global-config tabs (phase 4) and imported-plugin task pages (`ImportedTaskTab`, phase 5). A leading emoji in a task name becomes its tile.
4. **Settings, About, Update.** Done: `SettingsPage` (section list, appearance, one `ConfigSection` with its own Reset per global config), `GlobalConfigTab` on `ConfigSection`, and a kit `AboutTab`/`UpdateCard`. `SettingTab`, `GlobalConfigCard`, `VersionCard`, `LinksBar`, `ProjectCard` and `HttpTextEdit` are removed; theme and language still go through qfluentwidgets' `qconfig` until phase 6.
5. **Developer pages** – Debug becomes Diagnosis (`debug/diagnosis_page.py`), shown in every build: capture, OCR and thread dumps beside a screenshot viewer with a recent list and a Boxes/Original toggle; the connection popover's Capture opens it. Reload tasks, the i18n buttons and the Ctrl+Alt+D/S hotkeys stay debug-only, and the task-function caller is removed. Plugins, Templates, Script (Edit Task), Schedule and the MarkUp editor (now a `KitWindow` with a Features panel) are rebuilt on the kit. Imported plugin task pages are `TasksPage` subclasses listing the plugin's tasks; task-owned plugin pages sit in a plain container that keeps the plugin's own styling. Run Code is removed. The separate Log window is now the Log page under Run (`shell/log_page.py`): a `QPlainTextEdit` with a level highlighter, block-count trimming, batched appends and debounced plain-text refiltering, replacing full rich-HTML rebuilds; the connection popover's View Log opens it.
6. **Removal** – done: qfluentwidgets, PySideSix-Frameless-Window and darkdetect are gone from `pyproject`; the old task cards, `LabelAndX` editors, `ConfigCard`, `BaseWindow`, fluent `qss` resources and their tests are deleted. `ui_config.json` is read by a small `UiConfig` (language, theme; it still reads the old qfluentwidgets keys), `CustomTab`/`Tab`/`Card`/`StartLoadingDialog` and `MessageWindow` are kit-based, and `show_info_bar` shows a kit toast. `tests/test_headless_imports.py` imports every `ok.ui.qt` module with qfluentwidgets blocked. The redesign's strings are translated in all bundled languages. ok-wuthering-waves' `CharacterCodeTab` and `MultiAccountConfigTab` (qfluentwidgets, `ConfigCard`) must be ported before it runs on this version.

Out of scope: migrating ok-wuthering-waves, done later as a separate change.

## 5. Risks

- **Frameless window on Windows** (snap layouts, DPI changes, multi-monitor) is the hardest part of replacing qframelesswindow; keep a native-frame fallback setting.
- **Translations**: new strings for the redesigned pages; existing keys reused where wording is unchanged.
- **Plugin breakage** for third-party apps that import qfluentwidgets or pass Fluent icons; accepted, documented in the release notes and `docs/en/plugins.md`.
- **QSS limits** for animated or custom-painted controls (switch, progress ring, nav indicator) – these are painted widgets, not QSS.
