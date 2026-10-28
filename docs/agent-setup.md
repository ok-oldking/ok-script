# Set up ok-script with a coding agent

Use this entry point when asked to install the `ok-script` Python package, prepare
its environment, or set up an automation project that uses it. Work in the
consuming application's folder. The library source does not need to be cloned.

## Give the agent an entry point

For a one-time setup, tell your coding agent:

> Install ok-script and set up this project's environment. First read https://raw.githubusercontent.com/ok-oldking/ok-script/master/docs/agent-setup.md and follow the relevant setup skills linked there. Preserve this project's existing dependency constraints.

For future requests such as "install ok-script and set up its environment", add
the following to the consuming project's `AGENTS.md`, or the instruction file
your coding agent reads:

```markdown
## ok-script setup

When asked to install, configure, or repair ok-script or its Python environment,
read https://raw.githubusercontent.com/ok-oldking/ok-script/master/docs/agent-setup.md
and follow the relevant setup skills before changing the environment.
Use this project's virtual environment and preserve its dependency constraints.
After installation, offer to create an automation project and ask for missing
game/app details. Give each project its own subfolder, config, and start scripts.
```

Installing a Python package does not register its instructions with a coding
agent. The prompt or project instruction supplies the discovery link; after
installation, the package also provides local copies of the skills. No MCP
server is needed to read the setup instructions.

## Instructions for the coding agent

1. Inspect the consuming project's instructions, Python requirements, lockfile,
   existing environment, and requested outcome. This is application setup, not
   development of the ok-script library. For a new environment, ok-script
   currently requires Windows and Python 3.11 or later; check the selected
   release's package metadata for its requirements.
2. Read the
   [setup-env skill](https://github.com/ok-oldking/ok-script/blob/master/.agents/skills/setup-env/SKILL.md)
   before installing or repairing dependencies. It covers environment creation,
   optional dependency profiles, the separate OpenCV choice, and verification.
   If reading remotely, resolve that skill's relative links against its location
   in this repository. Preserve existing pins and use instructions from the
   matching release or local package when available.
3. Install in the application's environment and record the chosen dependencies
   in its existing dependency manifest or lockfile. Follow its package manager's
   workflow. Select only the profiles the requested application needs; a desktop
   GUI commonly uses `default,qt`, with exactly one compatible OpenCV variant
   installed separately. Verify the environment before offering project creation.
4. After a successful initial installation, ask: "Would you like to create an
   automation project now? Which game or app should it automate, and is it a
   Windows app or an Android device/emulator?" If the user already requested a
   project, ask only for missing details. Skip this offer when repairing an
   existing project or when the user has explicitly declined project creation.
5. When project creation is requested, read the
   [setup-project skill](https://github.com/ok-oldking/ok-script/blob/master/.agents/skills/setup-project/SKILL.md).
   Identify the actual executable/window or device/app from the user's answers
   and local inspection. Ask for any required details that remain ambiguous;
   wait for those answers before writing target-dependent config. Create each
   project in its own named workspace subfolder, containing its own `config.py`,
   `start_gui.py`, and `start_mcp.py`. Keep its tasks, assets, settings, and logs
   in that folder too. Omit `gui_icon` to use the default `OK` PNG bundled with
   the Python package; set it only when supplying a custom application icon.
   Reuse an existing project in place. Projects may share
   the prepared environment when compatible. Use the installed version's APIs
   and verify that launchers work when invoked from outside their subfolder.
6. Run the checks in the relevant skills. Report the environment path, installed
   ok-script version, dependency profiles, OpenCV choice, and verification
   results. For application setup, also report the project folder, config,
   launcher paths, and which target capture/input checks succeeded.

## Read skills from an installed package

Use the selected environment's interpreter to obtain skill metadata and absolute
source paths without starting the GUI or MCP server. This example runs from the
workspace containing `.venv`; a project subfolder can use that same interpreter
by its resolved absolute path:

```powershell
$projectPy = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $projectPy -c "from ok.core.skills import list_skills; import json; print(json.dumps(list_skills(), indent=2))"
```

Read the returned `setup-env` or `setup-project` path and resolve relative links
from that file. These local copies match the installed package. If an older
release does not include skills, use this repository's instructions and inspect
the installed APIs rather than upgrading just to obtain instructions.

Once a requested MCP runtime is running, `list_skills()` and
`get_skill("setup-project")` expose the same instructions. See the
[MCP guide](mcp.md) for connection details and the
[development prompts](en/agent-prompts.md) for subsequent task implementation.
