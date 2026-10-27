# Ask a coding agent to build reusable automation

[简体中文](../agent-prompts.md) · [Documentation](index.md) · [Connect MCP](quick_start.md)

Open the consuming application's folder in your local coding agent. Give it the project path, target application, and desired result. The agent needs local file/process access as well as access to the project's ok-script MCP server. Replace the example paths and task details below with your own.

## Connect to the project

> Work in E:\automation\my-app. Use this project's virtual environment and existing requirements. Start its ok-script MCP development launcher, or help configure one if missing. Read the live connection record under logs/mcp/connections, verify the project and process, and connect with its URL and bearer token without printing credentials. Call list_skills and read the relevant skills with get_skill. Confirm that screenshot captures the intended target. Do not use Computer Use skills, plugins, or tools.

If your agent has no native MCP connection, ask it to use the installed official MCP Python SDK from a local client script. It should still submit task files to the MCP server. See [connection details](../mcp.md) for ports, authentication, and lifecycle behavior.

## Get the APIs needed for a task

> Through ok-script MCP, call list_skills and read get_skill("develop") and any relevant template or test skill. I need to find a Settings button, click it, and verify the resulting screen. Locate the ok-script package used by this project's interpreter. Inspect the installed source, docstrings, and Python signatures for the required capture, matching, waiting, and input methods, including inherited methods. Report each method's import path, exact signature, return behavior, and local source location. Give a minimal example for this installed version. Do not invent API names or install a different version just to match an example.

MCP exposes workflow skills and execution tools; it does **not** expose a `get_api` tool or a full Python API catalog. The agent reads the installed package locally to obtain version-matched APIs. If importing a module needs an unavailable optional dependency, it can read the source before deciding whether that dependency is needed. A source checkout is not required.

## Develop and validate a new task

> In E:\automation\my-app, develop a reusable Python task named EnableOptionTask for my Windows application. Start from its home screen, open Settings, enable the option "Show details", save, reopen Settings, and verify that "Show details" is enabled. Running it again must leave the option enabled rather than toggle it off.
>
> Read the relevant MCP skills and inspect the installed APIs before implementation. Keep the implementation in a permanent project task module. Use ok-script APIs for capture and interaction, prioritizing verified PostMessage input. Prefer geometry, colors, or template matching; use OCR only if needed. Do not use Computer Use tools or add LLM calls to the runtime.
>
> Test through MCP with reset_to_start, verify_start_state, and an observable success assertion. Restore and verify the baseline before every attempt, save failure logs/screenshots, use bounded waits, and test repeat runs. Register the finished task in the project configuration and make recovery work for ordinary GUI/CLI execution as well as MCP. Give me the saved file paths, tested results, remaining limitations, and the exact command to run the task without an agent. Report any GUI Start-action check that could not be verified.

For another task, specify the same four things: **target, starting state, actions, success condition**. Include constraints such as supported resolutions, background operation, and actions the script must never take. The deliverable is reusable Python code and its assets, configuration, and run instructions.

## Fix an existing task

> The saved EnableOptionTask fails after the application's Settings layout changed. Call list_tasks to find its original source, inspect the failure evidence, and edit that implementation in place. Use reload_tasks with its returned task ID, wait for a successful reload, then restore the target and test through a thin MCP harness that invokes the registered task. Do not duplicate the task in a temporary script. Reuse its recovery code, verify repeated execution, and add a screenshot regression test if recognition changed. Keep the runtime free of LLM calls.

## Reuse the result

Ask the agent to provide the real registered task name and configuration target. A typical command, run from the application project, is:

```powershell
.\.venv\Scripts\python.exe -m ok run_task EnableOptionTask --config src.config:config
```

This CLI command selects a **registered task**, while MCP's `run_task(file_path)` executes a task file. They are different entry points. You can also start the saved task from the application's GUI with MCP disabled. Stop the development runtime before switching to normal execution; see the [quick start](quick_start.md).

The coding conversation consumes model tokens. Reusing local Python automation requires neither an agent nor LLM inference. A later UI change may require another development session; a script you explicitly design to call an LLM will have its own inference costs.
