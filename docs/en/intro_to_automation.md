# How reusable automation works

[简体中文](../intro_to_automation/README.md) · [Documentation](index.md) · [MCP quick start](quick_start.md)

A coding agent helps develop and validate the program. The saved Python program then performs the automation itself. This separates model-assisted development from ordinary execution, so repeated local runs do not require model tokens.

## During development

You describe the target application, starting state, steps, and visible success condition. Through MCP, the coding agent reads workflow skills, observes the target, submits Python task files, and checks their results. It uses local file access to inspect installed APIs, save the implementation, and diagnose logs and screenshots.

The agent repeats this process until the script works under the tested conditions. It keeps the behavior in a reusable project task, with configuration and recognition assets. Use ok-script capture and interaction throughout; do not use Computer Use tools.

## During ordinary execution

The saved Python task repeats a simple loop:

1. **Observe:** capture the target window or device screen.
2. **Recognize:** use geometry, colors, template matching, or OCR to identify the current state.
3. **Act:** send input through the configured ok-script backend.
4. **Verify:** inspect the resulting state and stop when the success condition is met.

The code controls the loop. A local OCR or image-recognition model does not require a conversational LLM. Scripts only incur LLM inference costs if you explicitly add LLM calls.

## Choose recognition for the task

| Technique | Useful for |
| --- | --- |
| Geometry and colors | Regular controls, highlights, progress bars |
| Template matching | Stable buttons and icons |
| OCR | Text whose content matters to the decision |
| Object detection | Objects whose appearance varies beyond fixed templates |

Ask the agent to start with the simplest reliable method and validate it against real screenshots. Templates and geometry can depend on resolution, scaling, animation, and UI changes. A successful run demonstrates the tested conditions, not every future version of the application.

## Make repetition reliable

A reusable task restores and verifies its starting state, uses bounded waits, records failures, and asserts the actual result. Repeated execution should preserve the desired outcome: an "enable option" task must not toggle it off on the next run.

Background input also needs validation. Ask the agent to prioritize PostMessage on Windows and verify real effects while the target is unfocused or covered. Working screenshots do not prove input works, and covered-window support does not prove minimized-window support.

## Your first task

Choose a small workflow such as opening Settings and enabling one option. Follow the [MCP quick start](quick_start.md), then copy a [task-development prompt](agent-prompts.md). Keep the resulting script and run it without the agent. When the UI changes, reconnect the agent and ask it to repair the existing task.
