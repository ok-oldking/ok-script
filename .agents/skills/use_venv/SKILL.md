---
name: use-venv
description: Select the consuming application's virtual environment for Python commands, task execution, tests, and package tools when using ok-script or its MCP server.
---

# Use the Application's Virtual Environment

Resolve the third-party application's root and use its virtual environment for Python commands, launchers, and tests. The directory containing this skill or the installed `ok` package is not the application root.

Honor an explicitly configured environment; otherwise prefer the application's `.venv`. Use an absolute interpreter path when changing directories, and preserve the application's dependency and test-runner conventions.

## PowerShell

From the application root, resolve the interpreter:

```powershell
$py = if (Test-Path .\.venv\Scripts\python.exe) { ".\.venv\Scripts\python.exe" } else { "python" }
```

Then run commands through that interpreter:

```powershell
& $py -m py_compile src\tasks\MyTask.py
& $py -m pytest tests
& $py .\start_mcp.py
& $py -m pip install -r requirements.txt
```

Do not call global `python`, `pip`, or `pytest` directly when `.venv` exists. Use `& $py`, `& $py -m pip`, and `& $py -m pytest` instead.

If the environment is absent or dependencies are missing, follow [setup-env](../setup-env/SKILL.md). Linking the `ok` source folder does not install its dependencies into another project's environment.
