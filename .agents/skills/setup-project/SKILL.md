---
name: setup-project
description: Create or configure an ok-script automation project, collect missing game or app details, and give each project its own subfolder, config, GUI and MCP start scripts, and Windows shortcut.
---

# Set Up a Local Automation Project

Work in the consuming application's directory at the user's requested location. Inspect an existing project before adding files. Use [setup-env](../setup-env/SKILL.md) when its environment needs preparation, and [docs/mcp.md](../../../docs/mcp.md) for current CLI and server configuration. Configure the application through the installed library's APIs; no ok-script source checkout is required.

## Collect the target details

When following an installation-only request, first ask whether the user wants a project, as described in `setup-env`. If they already requested a project, proceed without asking for the same confirmation again. Reuse details from the request and existing project, and ask a short grouped question for missing information:

- Which game or app should this project automate, and is it a Windows application or an Android device/emulator?
- For Windows, which installed executable or running window is the target? Inspect running processes and windows when possible; ask for the executable path or window choice when the target cannot be identified unambiguously. Determine whether the launcher should open the target or attach to an already-running instance. Automatic startup requires its actual launch path or command.
- For Android, which device or emulator and which app should be targeted? Inspect available devices and the installed library's configuration before asking for identifiers the agent can discover itself. Ask the user to choose when multiple targets match.

Use a sensible project folder name derived from the app unless the user supplies one. Use the current workspace as the parent unless another location was requested. Ask about additional requirements, such as background operation, only when they affect the requested setup. Select and verify capture/input backends using the installed APIs; the user need not know their technical names.

Wait for essential target details before writing target-dependent configuration. Do not use example executable names or window titles as if they were verified. If environment setup is still needed, it can proceed while the target question is pending.

## Layout and source access

Create each new automation project in its own named subfolder under the workspace. Each project must have its own `config.py`, `start_gui.py`, and `start_mcp.py` inside that subfolder. Keep its task modules, assets, mutable configuration, logs, and screenshots there too. For example:

```text
workspace/
  .venv/
  my-game/
    config.py
    start_gui.py
    start_mcp.py
    tasks/
    assets/
    configs/
    logs/
    screenshots/
  another-app/
    config.py
    start_gui.py
    start_mcp.py
```

Create supporting directories as needed. Reuse a matching existing project folder; if the current directory is already that project's folder, edit it in place rather than nesting another copy. Keep separate projects' config and launch scripts separate, even when they target the same app.

Ensure each application's root has `.agents/skills/ok-script-develop/SKILL.md`,
following the local skill generation instructions in [setup-env](../setup-env/SKILL.md).
Do this even when its environment is shared with the parent workspace, so an agent
opened directly in the application folder can discover development guidance.
Preserve existing project-specific skill content.

Projects may share the workspace environment just installed when their dependencies are compatible, or use a project-local environment when required. Record the chosen interpreter and use its absolute path in shortcuts and run instructions. Target launchers must work when invoked by absolute path from another working directory: resolve paths from `__file__`, make the project's task modules and config importable, and set the working directory to that project's subfolder before starting the runtime. Resolve mutable paths under that same folder so projects do not share settings, logs, or MCP ownership accidentally.

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

Adapt this example. BitBlt and PostMessage are initial candidates, not proof of target compatibility. Register a completed task as `['task_module', 'Task']` in `onetime_tasks`, using an import path available to both launchers.

If the task needs named template matching, add `template_matching` with
`'template_folder': str(ROOT / 'assets' / 'templates')` and the project's matching
settings. Keep an existing `coco_feature_json` entry when packed assets are still
used; both sources can coexist. Keep editable screenshots and COCO annotations
under `ok_templates`, separate from exported crops. Follow
[generate-templates](../generate-templates/SKILL.md) for export and verification.

## Separate launchers

- `start_gui.py` is the user entry point. Explicitly select the Qt GUI and disable MCP. Launch it with the project's `pythonw.exe`. Redirect absent stdout/stderr to a local startup log so startup errors remain observable without a console.
- `start_mcp.py` is the coding agent entry point. Enable MCP and normally run headless; support a configurable port when useful. If GUI-assisted development is needed, keep that entry point separate from the user launcher. The agent can start the process itself; do not require the user to open a console.
- Keep both scripts in the project's subfolder and load that project's `config.py`. Share path setup and target process startup in a project-local launcher helper when useful. Copy config before applying mode-specific overrides. Clean up the runtime on exit.
- A user `.lnk` targets the absolute venv `pythonw.exe`, passes a quoted absolute `start_gui.py` path, and sets the working directory. Use a custom shortcut icon when one is supplied. A hidden `python.exe` console does not replace `pythonw.exe` for the user shortcut.

Starting a GUI replaces the registered console owner for the same working directory, closing that console's MCP server. Keep both launchers in the same target directory so project ownership matches. Close the GUI before starting a console development session. Never kill arbitrary Python processes to free a port; identify the owning project and PID.

## Verify against the real target

Start the development launcher and inspect an MCP screenshot for a complete, current target image. Test reset, left/right clicks, keys, or other required input against observable UI changes. Prioritize PostMessage, checking background operation while the target is unfocused or covered and confirming that foreground focus and the cursor remain undisturbed. Do not infer minimized-window support from those checks.

If capture is cropped or stale, inspect backend behavior and DPI/coordinate scaling before changing recognition code. For a legacy application, a child-only `HIGHDPIAWARE` compatibility environment may help; apply it only when verified, rather than globally changing Windows settings.

Launch the actual user shortcut: confirm the GUI opens without a console or MCP listener and loads this project's config. When a task was also requested and implemented, confirm it appears with a useful name and its Start action runs successfully; see [develop](../develop/SKILL.md) for task lifecycle and retry behavior. A new project without tasks should still open successfully. Report the project folder, config, selected interpreter, concrete launcher paths, and the interaction/capture behavior that was tested.
