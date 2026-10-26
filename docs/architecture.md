# Runtime architecture

`ok-script` has one framework-neutral runtime and optional UI adapters.

```
ok/core/          events, task discovery, startup, screenshots, downloads, translations
ok/task/          automation task and executor logic
ok/device/        capture and interaction logic
ok/ui/qt/         PySide6 and PySide6-Fluent-Widgets desktop UI
ok/gui/           compatibility namespace for existing imports
```

Core modules publish through `ok.core.events.communicate`. An event signal has a
small `connect`, `disconnect`, and `emit` API without depending on a UI toolkit.
The Qt adapter installs a main-thread dispatcher so subscribers run on the UI
thread.

Imported plugin manifests may declare tasks and custom Qt tabs. The Qt adapter
owns page creation and disposal; the core loader and release downloader remain
independent of Qt. See [imported plugins](en/plugins.md) for the opt-in manager,
package format, and task-owned page factories.

## Install a mode

```bash
pip install ok-script                # minimal headless core
pip install "ok-script[default]"     # headless runtime profile
pip install "ok-script[qt]"          # desktop UI
pip install "ok-script[adb]"         # ADB devices
pip install "ok-script[ocr]"         # ONNX OCR
pip install "ok-script[mcp]"         # localhost agent tools
```

OpenCV is not part of any profile. Users must choose the version and exactly one
suitable variant for their application: `opencv-python`,
`opencv-contrib-python`, `opencv-python-headless`, or
`opencv-contrib-python-headless`.

The optional-dependency profiles and local TOML dependency groups have identical
names and requirements. For headless repository development, install:

```bash
pip install --editable . --group default --group dev
```

Add the `qt`, `adb`, or `ocr` group for the use case being developed.

## Run a mode

```bash
ok run_task DailyTask --config src.config:config
ok gui --config src.config:config
ok mcp --config src.config:config
```

GUI startup takes over the registered console instance of the same project
working directory. The instance marker records its PID, creation time, mode,
and interpreter, allowing `pythonw.exe` GUI entry points to replace a development
`python.exe` process even when they use separate launcher scripts. Process
creation time protects against stale markers referring to reused PIDs.

New desktop imports should use `ok.ui.qt`. Existing `ok.gui` imports remain
available as a migration shim.

The optional `mcp` profile provides a localhost development server with four
tools for running task files, checking status, stopping, and observing the UI.
See [MCP task development](mcp.md) for the task contract and local artifacts.
