---
name: setup-env
description: Create or repair a third-party application's environment for the ok-script library, GUI, or MCP server using the application's dependency requirements.
---

# Set Up the Local Environment

Work in the consuming application's directory and use its configured environment or `.venv`. Inspect its requirements, lockfile, supported Python versions, and installed packages before changing dependencies. Installing and using ok-script does not require a library source checkout.

## Interpreter and dependencies

- Resolve an existing `.venv\Scripts\python.exe` before any Python command. Use an absolute path when commands change directories. Use `-m pip`, `-m pytest`, and `-m py_compile` through that interpreter.
- If a new environment is needed, create it with an available interpreter compatible with the application's requirements and its chosen ok-script release. Inspect installed distribution metadata with `importlib.metadata` when needed. Do not recreate a working environment just to install missing packages.
- Prefer the application's requirements or lockfile and preserve its chosen ok-script version. Select `default` for the normal vision/capture stack, `qt` for the desktop GUI, `mcp` for the local server, `adb` for Android targets, and `ocr` when required. A GUI application tested through MCP normally needs `default`, `qt`, and `mcp`. Install application test dependencies only when its tests need them.
- OpenCV is deliberately separate from these profiles. Inspect the installed `opencv-*` packages and choose exactly one compatible variant. Reuse the project's existing choice when suitable; do not install multiple variants that all provide `cv2`.

For an installed release, select the extras actually needed, for example:

```powershell
$projectPy = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $projectPy -m pip install 'ok-script[default,qt,mcp]'
```

Run this from the application's root. Install the chosen OpenCV variant separately if it is absent.

If the application intentionally uses an existing editable library installation or `ok` source link, preserve that arrangement and install its required dependencies in the application's environment. A source link alone does not install dependencies. Modify the application's tasks and configuration; library source changes are outside this skill's scope.

Use the normal package index first. If downloads stall, a reachable alternate index can be supplied to the individual pip command; do not change persistent pip configuration as a side effect of setup.

## Verify the environment

Run `& $projectPy -m pip check`. Smoke-test `import ok, cv2` and the selected optional stacks, and verify `ok.__file__` resolves to the intended checkout or installed package. For MCP, also check `import mcp`; for Qt, check `from PySide6 import QtCore` and `import qfluentwidgets`.

Run the application's launcher with its environment to catch runtime imports that dependency metadata alone cannot verify. Compile changed application scripts and run its existing tests when relevant.

Report the environment path, dependency profiles, OpenCV choice, and verification outcome. Continue with [setup-project](../setup-project/SKILL.md) when a target and launchers are also requested.
