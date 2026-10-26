# AI Coding Instructions

## Repository Skills

Read the applicable skill before doing the corresponding work:

| Work | Skill |
| --- | --- |
| Create or repair a virtual environment; install missing dependencies | [setup-env](.agents/skills/setup-env/SKILL.md) |
| Configure a local target, source link, GUI/MCP launchers, or shortcut | [setup-project](.agents/skills/setup-project/SKILL.md) |
| Implement or debug automation tasks locally or through MCP | [develop](.agents/skills/develop/SKILL.md) |
| Select the interpreter for Python commands | [use-venv](.agents/skills/use_venv/SKILL.md) |

## Python Environment

When running Python commands in this repository, prefer the repository virtual environment if it exists.

On Windows PowerShell, use:

```powershell
$py = if (Test-Path .\.venv\Scripts\python.exe) { ".\.venv\Scripts\python.exe" } else { "python" }
& $py -m pytest
```

For direct scripts, use `& $py path\to\script.py`. For package tooling, use `& $py -m pip`, `& $py -m pytest`, and `& $py -m py_compile`.

Do not use the global `python` when `.\.venv\Scripts\python.exe` exists, unless the user explicitly asks for the global interpreter.

A separate automation project uses its own `.venv`. Use the framework environment for framework checks and the project environment for its runtime. Install only the dependency profiles needed by the target; OpenCV is a separate choice of exactly one variant.

## Local Automation Development

The coding agent can start the local runtime, edit task files, and inspect local logs and screenshots directly. Keep automation in Python files and submit their absolute paths through MCP. See [docs/mcp.md](docs/mcp.md) for the current tools and task contract.

Before every attempt, restore the target application's starting state and verify it. Reuse existing recovery functions when possible; otherwise implement recovery in the task. A capture cache reset does not restore application state. Record diagnostics and assert the actual success condition in task code.

Prioritize PostMessage for Windows background interaction, and verify its effects against the real target before relying on it. Prefer visual geometry, colors, or template matching for simple UI elements; add OCR only when it solves a demonstrated need.

Use separate user GUI and agent MCP launchers. The user shortcut uses `pythonw.exe`, has no console, and keeps MCP disabled. Starting a GUI replaces the verified console owner for the same project; do not terminate unrelated Python processes. Register finished tasks in the project config and verify they run from the GUI as well as MCP.
