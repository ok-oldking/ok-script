---
name: setup-project
description: Set up a third-party automation application using ok-script, with its own environment, configuration, GUI and MCP launchers, and Windows shortcut.
---

# Set Up a Local Automation Project

Work in the consuming application's directory at the user's requested location. Inspect an existing project before adding files. Use [setup-env](../setup-env/SKILL.md) when its environment needs preparation, and [docs/mcp.md](../../../docs/mcp.md) for current CLI and server configuration. Configure the application through the installed library's APIs; no ok-script source checkout is required.

## Layout and source access

A playground can share one environment with a subfolder per target. Keep each target's config, task modules, assets, logs, screenshots, and entry points together. Target launchers must work when invoked by absolute path from another working directory: resolve paths from `__file__`, make the application's task modules importable, and set the working directory to the target folder.

Prefer the application's installed ok-script dependency. If the user explicitly requests a source link to an existing library installation, link `<project-root>\ok` to that checkout's `ok` directory and add the link's parent to `sys.path` before importing `ok`. Prefer a directory symbolic link; if Windows denies symlink privileges, use a directory junction. Verify existing destinations and resolved paths before replacing anything; never recursively delete through the link. This is dependency access, not permission to modify library code.

When obtaining a requested test application, record its source and checksum, verify the file type, and preserve existing downloads. Reuse an existing process only when its resolved executable path matches the intended target.

## Application config

Build a project-local config using the actual target's executable, title, capture backend, and interaction backend. Resolve mutable paths under the target folder. A Windows GUI project commonly has:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parent
config = {
    'version': '0.1.0',
    'gui_title': 'Automation Playground',
    'gui_icon': str(ROOT / 'assets' / 'app.png'),
    'gui': {'type': 'qt'},
    'debug': False,
    'config_folder': str(ROOT / 'configs'),
    'screenshots_folder': str(ROOT / 'screenshots'),
    'windows': {
        'exe': ['target.exe'],
        'title': 'Target Window',
        'capture_method': ['BitBlt'],
        'interaction': 'PostMessage',
        'start_exe': True,
        'calculate_pc_exe_path': str(ROOT / 'target.exe'),
    },
    'onetime_tasks': [],
    'trigger_tasks': [],
    'mcp': {
        'enabled': False,
        'port': 8765,
        'artifact_directory': str(ROOT / 'logs' / 'mcp'),
    },
}
```

Adapt this example; ship an actual valid icon if configuring `gui_icon`. BitBlt and PostMessage are initial candidates, not proof of target compatibility. Register a completed task as `['task_module', 'Task']` in `onetime_tasks`, using an import path available to both launchers.

## Separate launchers

- `start_gui.py` is the user entry point. Explicitly select the Qt GUI and disable MCP. Launch it with the project's `pythonw.exe`. Redirect absent stdout/stderr to a local startup log so startup errors remain observable without a console.
- `start_mcp.py` is the coding agent entry point. Enable MCP and normally run headless; support a configurable port when useful. If GUI-assisted development is needed, keep that entry point separate from the user launcher. The agent can start the process itself; do not require the user to open a console.
- Share path setup and target process startup in a launcher helper. Copy config before applying mode-specific overrides. Clean up the runtime on exit.
- A user `.lnk` targets the absolute venv `pythonw.exe`, passes a quoted absolute `start_gui.py` path, and sets the working directory and icon. A hidden `python.exe` console does not replace `pythonw.exe` for the user shortcut.

Starting a GUI replaces the registered console owner for the same working directory, closing that console's MCP server. Keep both launchers in the same target directory so project ownership matches. Close the GUI before starting a console development session. Never kill arbitrary Python processes to free a port; identify the owning project and PID.

## Verify against the real target

Start the development launcher and inspect an MCP screenshot for a complete, current target image. Test reset, left/right clicks, keys, or other required input against observable UI changes. Prioritize PostMessage, checking background operation while the target is unfocused or covered and confirming that foreground focus and the cursor remain undisturbed. Do not infer minimized-window support from those checks.

If capture is cropped or stale, inspect backend behavior and DPI/coordinate scaling before changing recognition code. For a legacy application, a child-only `HIGHDPIAWARE` compatibility environment may help; apply it only when verified, rather than globally changing Windows settings.

Launch the actual user shortcut: confirm the GUI opens without a console or MCP listener, the task appears with a useful name, and its Start action runs successfully. See [develop](../develop/SKILL.md) for task lifecycle and retry behavior. Report concrete launcher paths and the interaction/capture behavior that was tested.
