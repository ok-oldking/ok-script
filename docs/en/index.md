---
hide:
  - navigation
  - toc
---

<div class="ok-hero" markdown>

# Vibe Coding Automation Framework

**Make a wish in Codex, Claude Code, or any coding agent with MCP, and get a deployable automation app.**

Through MCP, the agent observes your Windows application, game, or Android device, writes Python tasks, runs them against the real target, and fixes what fails. ok-script packages the finished tasks with a desktop GUI into a Windows installer you can ship. The packaged app runs on its own; no agent stays connected.

[Start with MCP](quick_start.md){ .md-button .md-button--primary }
[Copy agent prompts](agent-prompts.md){ .md-button }
[简体中文](../index.md){ .md-button }

</div>

## How MCP development works

The agent edits files and reads logs with its own tools. MCP gives it the running application.

<div class="grid cards" markdown>

-   :material-book-open-variant:{ .lg .middle } __1. Learn__

    ---

    `list_skills` and `get_skill` return the development, template, test, and reload workflows bundled with the installed ok-script version. The agent reads exact Python signatures from the installed package.

-   :material-monitor-screenshot:{ .lg .middle } __2. Observe__

    ---

    `screenshot` saves the current frame of the configured window or device, so the agent sees what the task will see.

-   :material-play-circle:{ .lg .middle } __3. Run__

    ---

    `run_task` executes a Python task file against the real target. Every attempt restores and verifies the starting state before `run()` performs and asserts the automation.

-   :material-file-search:{ .lg .middle } __4. Inspect__

    ---

    Each attempt writes `run.log`, `status.json`, and task screenshots under `logs/mcp/<run_id>/`. `get_run_status` reports progress and errors; `stop_task` cancels.

-   :material-wrench:{ .lg .middle } __5. Repair__

    ---

    `list_tasks` returns registered task sources. After editing, `reload_tasks` replaces them in the running process. `exit_process` ends a runtime that cannot be reset.

-   :material-rocket-launch:{ .lg .middle } __6. Ship__

    ---

    Register the task, run it from the GUI or `python -m ok run_task`, and package the app as a Windows installer with [PyAppify](https://github.com/ok-oldking/pyappify). See [packaging and releases](advanced.md).

</div>

## What to ask the agent

=== "Build a task"

    > Connect to this project's ok-script MCP server and read its development skill. Inspect the installed capture, matching, and input APIs and show their exact signatures and source locations. Build a reusable Python task that opens Settings, enables "Show details", saves, and verifies the result. Restore and verify the starting screen before every attempt, test repeated runs, and save the task in the project. Use ok-script APIs and MCP, not Computer Use tools. Give me the exact command to run the finished task without an agent or LLM calls.

=== "Repair a task"

    > Connect to this project's ok-script MCP server and read its reload-tasks skill. Use list_tasks to find the source of the failing task, fix that file, reload its task ID, and wait for the reload to succeed. Restore and verify the starting screen, run the registered implementation repeatedly, and show me the evidence from the run logs and screenshots.

=== "Set up the environment"

    > Install ok-script and set up this project's environment. First read https://raw.githubusercontent.com/ok-oldking/ok-script/master/docs/agent-setup.md and follow its setup skills. Preserve this project's existing dependency constraints.

More examples, including API-only discovery, are in [agent prompts](agent-prompts.md).

## Connect in three steps

```powershell
.\.venv\Scripts\python.exe -m pip install "ok-script[default]"
.\.venv\Scripts\python.exe -m ok mcp --config src.config:config
```

1. Start the runtime with the project's configuration, or enable **Settings > Basic Options > Enable MCP Server** in an existing desktop application.
2. Read the URL and token from the live `logs/mcp/connections/<pid>-<port>.json` record.
3. Configure the agent's MCP client for Streamable HTTP with the header `Authorization: Bearer <token>`.

!!! warning "Local developer access"
    The server listens only on local loopback, but connected agents can run Python with your account's permissions. Keep the token private and use a separate MCP-disabled launcher for everyday use.

## Guides

<div class="grid cards" markdown>

-   :material-flag-checkered:{ .lg .middle } __Start MCP development__

    ---

    [MCP quick start](quick_start.md) · [Agent environment setup](../agent-setup.md) · [Ask a coding agent](agent-prompts.md)

-   :material-api:{ .lg .middle } __MCP reference__

    ---

    [Connection and execution](../mcp.md): tools, run states, reloads, diagnostics, and the task file contract. [Template export format](../feature-crops.md).

-   :material-package-variant-closed:{ .lg .middle } __Ship and maintain__

    ---

    [Maintain and share tasks](advanced.md): templates, regression tests, localization, and packaging. [Imported plugins](plugins.md).

-   :material-cog-outline:{ .lg .middle } __Concepts and tools__

    ---

    [How automation works](intro_to_automation.md) · [Interface and developer tools](interface.md) · [Runtime architecture](../architecture.md)

</div>

API discovery happens against the version installed in your project. Ask the agent to read its source and signatures rather than copying a static API reference.
