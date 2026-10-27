# ok-script: spend tokens once, reuse the automation

[简体中文](../index.md) · [Project home](https://github.com/ok-oldking/ok-script)

Use a coding agent to turn a task description into a reusable Python automation script. Connect the agent to ok-script through MCP so it can observe your application, run the script, inspect failures, and verify the result. Keep the finished code and run it whenever you need it.

**Spend tokens on development; run the resulting Python automation without an LLM.** Development may take several iterations, and later application changes may need another coding session. Ordinary runs of scripts that use local recognition and input do not require model calls or tokens.

## Start with MCP

1. Open your automation project's folder in a local coding agent that supports MCP and local file/process access.
2. Follow the [quick start](quick_start.md) to install the runtime and connect its local MCP server.
3. Describe the target, starting state, actions, and observable success condition.
4. Let the agent discover skills, inspect the installed APIs, write Python, and test through MCP.
5. Run the saved task from your application's GUI or command line without keeping the agent connected.

## What to ask the agent

> Connect to this project's ok-script MCP server. Read the development skill and inspect the installed package for the capture, template matching, and input APIs needed for my task. Show the verified signatures and source locations before using them. Then implement a reusable Python task that opens Settings, enables my chosen option, saves it, and verifies that the option remains enabled. Restore and verify the starting screen before every attempt. Use ok-script capture and interaction, not Computer Use tools. Save the task in this project and give me the command to run it without an agent.

See [agent prompts](agent-prompts.md) for separate API discovery, task development, and maintenance examples.

## Guides

| Guide | Purpose |
| --- | --- |
| [MCP quick start](quick_start.md) | Set up a project, connect the agent, and run the saved task |
| [Ask a coding agent](agent-prompts.md) | Copyable prompts for API discovery and reusable tasks |
| [MCP connection and execution](../mcp.md) | Connection details, skill discovery, task runs, reloads, and diagnostics |
| [How automation works](intro_to_automation.md) | Understand the Python capture–recognize–act loop |
| [Interface and developer tools](interface.md) | Run saved tasks and inspect their visual evidence |
| [Maintain and share tasks](advanced.md) | Templates, regression tests, localization, and packaging |
| [Imported plugins](plugins.md) | Install and distribute reusable task packages |
| [Build this documentation](building-site.md) | Preview and validate the site |

API discovery happens against the version installed in your project. Ask the agent to read its source and signatures rather than copying a static API reference.
