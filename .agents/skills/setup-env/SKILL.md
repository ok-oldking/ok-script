---
name: setup-env
description: Create or repair an ok-script virtual environment and install the dependency profiles needed for a local automation target, GUI, or MCP development runtime.
---

# Set Up the Local Environment

Use the intended project's `.venv`. A framework checkout and a sibling automation project can have separate environments even when they share the `ok` source code. Inspect existing requirements and installed packages before changing them.

## Interpreter and dependencies

- Resolve an existing `.venv\Scripts\python.exe` before any Python command. Use an absolute path when commands change directories. Use `-m pip`, `-m pytest`, and `-m py_compile` through that interpreter.
- If a new environment is needed, create it with an available supported interpreter (see `requires-python` in [pyproject.toml](../../../pyproject.toml)). Prefer the checkout's interpreter to create a sibling project's venv. Do not recreate a working environment just to install missing packages.
- Treat `pyproject.toml` as the dependency source of truth. Core dependencies apply even when the project imports `ok` through a source link. Select `default` for the normal vision/capture stack, `qt` for the desktop GUI, `mcp` for the development server, `adb` for Android targets, `ocr` when required, and `dev` for framework tooling. A GUI project developed through MCP normally needs `default`, `qt`, and `mcp`.
- OpenCV is deliberately separate from these profiles. Inspect the installed `opencv-*` packages and choose exactly one compatible variant. Reuse the project's existing choice when suitable; do not install multiple variants that all provide `cv2`.

For an installed release, select the extras actually needed, for example:

```powershell
$projectPy = 'E:\projects\my-automation\.venv\Scripts\python.exe'
& $projectPy -m pip install 'ok-script[default,qt,mcp]'
```

Replace the example path with the actual project. Install the chosen OpenCV variant separately if it is absent.

For live checkout development, choose one approach:

- Install the checkout editable into the target environment, with the selected dependency groups. Run pip from the checkout directory; for example `& $projectPy -m pip install --editable . --group default --group qt --group mcp`. Check that pip supports dependency groups, upgrading pip only if needed.
- When the project uses an `ok` source link, install core dependencies and the selected optional-dependency lists from the checkout's `pyproject.toml` into the target venv. Generate or update the project's requirements from those lists and the selected OpenCV dependency; preserve its additional requirements. There is no need to install a second released copy of `ok-script` just to obtain its dependencies.

The checkout's build reads `OK_SCRIPT_BUILD_VERSION`; without it, `setup.py` attempts an online version lookup. If an editable development install needs a deterministic version, set a valid local version such as `0.0.0+local` for that command and restore the previous environment value afterward. A source link avoids package metadata builds.

Use the normal package index first. If downloads stall, a reachable alternate index can be supplied to the individual pip command; do not change persistent pip configuration as a side effect of setup.

## Verify the environment

Run `& $projectPy -m pip check`. Smoke-test `import ok, cv2` and the selected optional stacks, and verify `ok.__file__` resolves to the intended checkout or installed package. For MCP, also check `import mcp`; for Qt, check `from PySide6 import QtCore` and `import qfluentwidgets`.

Run the relevant launcher with the target venv to catch runtime imports that dependency metadata alone cannot verify. Compile changed scripts and run appropriate existing tests for code changes; do not install framework test tooling into every runtime venv just for convenience.

Report the environment path, dependency profiles, OpenCV choice, and verification outcome. Continue with [setup-project](../setup-project/SKILL.md) when a target and launchers are also requested.
