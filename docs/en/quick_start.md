# MCP quick start

[简体中文](../quick_start/README.md) · [Documentation](index.md) · [Agent prompts](agent-prompts.md)

Build the automation with a coding agent, then keep running the saved Python task. You need Windows, Python 3.11 or later, a target application or ADB device, and a local coding agent with MCP and file/process access.

## 1. Open an application project

Use your existing ok-script application, or create a project from the [ok-script-app template](https://github.com/ok-oldking/ok-script-app). Open its folder in your coding agent. Keep application tasks in this project, separate from the ok-script framework repository.

Ask the agent:

> Prepare this automation project's virtual environment and dependencies. Preserve its existing requirements and ok-script version. Configure my target application and separate MCP development and user GUI launchers. Use the bundled setup-env and setup-project skills when available. Do not use Computer Use tools.

For a new environment, the basic commands are:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "ok-script[default,mcp]"
```

For an existing application, install its requirements first and add the MCP extra for the same ok-script version. Add `qt`, `adb`, or `ocr` only as needed. OpenCV is a separate dependency: choose exactly one compatible variant, such as `opencv-python` or `opencv-python-headless`. The agent should use your project's existing choice.

The project also needs a configuration for the real target. Ask the agent to inspect the installed configuration handling and existing examples, then set the application's executable/window or ADB package and verify capture and input. Installing the package alone does not create a configured project.

## 2. Start the MCP runtime

Prefer the project's existing development launcher. Otherwise, from the application directory:

```powershell
.\.venv\Scripts\python.exe -m ok mcp --config src.config:config
```

Replace `src.config:config` with the project's actual module and configuration object. Leave the runtime running while the agent develops. This mode runs without Qt and pauses the regular scheduler.

An existing desktop application can also enable MCP through **Settings > Basic Options > Enable MCP Server** when the MCP dependency is installed. Review the application's access warning before enabling it. Use a separate MCP-disabled GUI launcher for ordinary use.

## 3. Connect the coding agent

Use the live record in `logs/mcp/connections/<pid>-<port>.json` under the project's configured artifact directory. It contains the server URL, bearer token, process identity, and project directory. The default port is 8765, but it may change; do not assume it.

Configure the agent's MCP client with:

| Setting | Value |
| --- | --- |
| Transport | Streamable HTTP |
| URL | The live record's `url` |
| HTTP header | `Authorization: Bearer <token from the live record>` |

Client configuration formats differ. Ask your coding agent to configure its supported MCP connection using these values, keeping the token private. The server listens on local loopback, so run the agent on the same machine with access to the project files. An agent without a native connection can use a local client script with the official MCP Python SDK.

Have the agent call `list_skills()`, read `get_skill("develop")`, and request `screenshot()` to confirm the target. If it captures the wrong application or cannot capture, fix the project configuration before attempting the task. More details are in the [MCP guide](../mcp.md).

## 4. Ask for a reusable task

> Use this project's MCP connection to build a reusable Python task that opens Settings, enables "Show details", saves, and verifies that the option stays enabled. Read the relevant skills and inspect installed API signatures. Save the implementation in a permanent task module. Restore and verify the baseline before each MCP attempt, record logs/screenshots, assert the visible result, and test repeated runs. Use ok-script capture and input, not Computer Use. Register the result and make it run without an agent or LLM calls.

The agent writes files locally and submits their absolute paths through MCP. For existing tasks it discovers the original source, edits it, reloads the registered task, and waits for successful reload before testing. See [copyable prompts](agent-prompts.md) for API discovery and maintenance requests.

## 5. Run without the agent

Ask the agent for the exact task name and launcher for your project. The saved task must be registered and perform its own preparation in normal execution; the GUI/CLI do not automatically invoke the MCP reset hooks.

Stop the MCP development runtime and wait for it to exit before ordinary CLI execution. For the same project, starting the GUI replaces the registered console runtime and closes its MCP connection. Do not switch modes during an active attempt. Typical commands are:

```powershell
.\.venv\Scripts\python.exe -m ok run_task EnableOptionTask --config src.config:config
.\.venv\Scripts\python.exe -m ok gui --config src.config:config
```

Choose the CLI or GUI command; do not run both simultaneously. The CLI selects a registered task name/class, not a Python file path. For everyday GUI use, prefer the application's MCP-disabled `pythonw.exe` launcher or shortcut. Qt dependencies are required for the GUI.

Keep the task source, configuration, recognition assets, and dependency requirements together. Normal runs of local Python recognition and input require no model tokens. Return to the coding agent when you need a new task or a repair.
