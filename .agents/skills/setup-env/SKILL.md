---
name: setup-env
description: Install the ok-script Python package and create or repair a consuming application's virtual environment, including dependencies for its GUI or MCP server.
---

# Set Up the Local Environment

Work in the consuming application's directory and use its configured environment or `.venv`. Inspect its requirements, lockfile, supported Python versions, and installed packages before changing dependencies. Installing and using ok-script does not require a library source checkout.

Use this skill for requests such as "install ok-script and set up its environment", even before an MCP server exists. Read this file directly from the repository or installed package; starting MCP is not a prerequisite. After installation and verification, generate the local development skill before the project-creation handoff below.

## Interpreter and dependencies

- Resolve an existing `.venv\Scripts\python.exe` before any Python command. Use an absolute path when commands change directories. Use `-m pip`, `-m pytest`, and `-m py_compile` through that interpreter.
- If a new environment is needed, create it with an available interpreter compatible with the application's requirements and its chosen ok-script release. Current releases require Windows and Python 3.11 or later. Inspect installed distribution metadata with `importlib.metadata` when needed. Do not recreate a working environment just to install missing packages.
- Prefer the application's requirements or lockfile and preserve its chosen ok-script version. Select `default` for the normal vision/capture stack, `qt` for the desktop GUI, `adb` for Android targets, and `ocr` when required. A GUI application tested through MCP normally needs `default` and `qt`. MCP is a required dependency starting in ok-script 2.0.17; older pinned releases may still need their `mcp` extra. Install application test dependencies only when its tests need them.
- OpenCV is deliberately separate from these profiles. Inspect the installed `opencv-*` packages and choose exactly one compatible variant. Reuse the project's existing choice when suitable; do not install multiple variants that all provide `cv2`.

For an installed release, select the extras actually needed, for example:

```powershell
$projectPy = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $projectPy -m pip install 'ok-script[default,qt]'
```

Run this from the application's root. Install the chosen OpenCV variant separately if it is absent.

Record the selected ok-script version or constraint, extras, and OpenCV variant in the application's existing dependency manifest or lockfile using its package manager. Keep setup reproducible without replacing unrelated dependencies.

If the application intentionally uses an existing editable library installation or `ok` source link, preserve that arrangement and install its required dependencies in the application's environment. A source link alone does not install dependencies. Modify the application's tasks and configuration; library source changes are outside this skill's scope.

Use the normal package index first. If downloads stall, a reachable alternate index can be supplied to the individual pip command; do not change persistent pip configuration as a side effect of setup.

## Verify the environment

Run `& $projectPy -m pip check`. Smoke-test `import ok, cv2, mcp` and the selected optional stacks, and verify `ok.__file__` resolves to the intended checkout or installed package. For Qt, check `from PySide6 import QtCore` and `import qfluentwidgets`.

If the application already has a launcher, run it with its environment to catch runtime imports that dependency metadata alone cannot verify. Compile changed application scripts and run its existing tests when relevant.

Report the environment path, dependency profiles, OpenCV choice, and verification outcome.

## Generate the project-local development skill

After successful installation, create
`<cwd>/.agents/skills/ok-script-develop/SKILL.md` in the consuming workspace where
the user requested setup. This is part of agent setup, including installation-only
requests; it does not depend on accepting project creation or starting MCP. When
repairing an environment, add the skill if it is missing.

Use [the generic development skill template](assets/ok-script-develop/SKILL.md)
as the initial content. Prefer the template shipped with the selected installed
release; locate this `setup-env` skill through `ok.core.skills.list_skills()` and
resolve `assets/ok-script-develop/SKILL.md` from its parent directory. If the
installed release predates the template, use the template accompanying these
setup instructions without upgrading the dependency.

Create the destination directory as needed and write the template as UTF-8. If
the destination already exists, read it first and preserve its project-specific
guidance; merge missing discovery instructions only when needed. Do not replace
a customized skill with the generic template. Keep the template's generic name
and description for new skills; do not copy game-specific observations, fixed
machine paths, or unrelated application skills from another project.

The generated skill discovers the library's version-matched instructions in place;
do not copy the full consumer skill catalog into the application. Verify the
generated file has its `name` and `description` frontmatter, and that its discovery
instructions locate this environment's `develop/SKILL.md`. Report the generated
or reused skill's path with the environment results.

## Offer to create a project

After a successful initial installation, ask whether the user wants to create an automation project and which game or app it should target. For example: "ok-script is installed. Would you like to create an automation project now? If so, which game or app, and is it a Windows app or an Android device/emulator?" Wait for the answer before creating a project that has not already been requested.

If project creation was already requested, continue with [setup-project](../setup-project/SKILL.md) and ask only for missing target/configuration details. That skill creates each project in its own subfolder with its own config and start scripts. Reuse the environment just prepared when compatible, adding any target-specific dependencies that become necessary.

Do not repeat this offer when repairing an existing project's environment, returning to an ongoing `setup-project` workflow, or when the user has explicitly declined project creation. An installation request by itself should receive the offer; a running MCP server is not required for this conversation.
