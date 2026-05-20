# AI Coding Instructions

## Python Environment

When running Python commands in this repository, prefer the repository virtual environment if it exists.

On Windows PowerShell, use:

```powershell
$py = if (Test-Path .\.venv\Scripts\python.exe) { ".\.venv\Scripts\python.exe" } else { "python" }
& $py -m pytest
```

For direct scripts, use `& $py path\to\script.py`. For package tooling, use `& $py -m pip`, `& $py -m pytest`, and `& $py -m py_compile`.

Do not use the global `python` when `.\.venv\Scripts\python.exe` exists, unless the user explicitly asks for the global interpreter.
