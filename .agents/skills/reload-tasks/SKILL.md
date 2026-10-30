---
name: reload-tasks
description: Modify a third-party application's registered ok-script tasks in place and reload them through MCP, preserving registration and verifying replacements before testing.
---

# Modify and Reload Existing Tasks

Prefer this workflow when changing an existing task in an application that uses ok-script. Edit the application's task source and reload its registered instance; keep new task files for new functionality. Library/server implementation changes are outside this skill's scope. Read [develop](../develop/SKILL.md) for target recovery, visual verification, and GUI validation, and [docs/mcp.md](../../../docs/mcp.md) for connection details.

## Edit and reload

1. Call `list_tasks()` to discover registered tasks. Use the returned `task_id` (the full module and class name) and absolute `file_path`; inspect the source and project config before editing.
2. Wait for any active MCP run to reach `succeeded`, `failed`, or `cancelled`. A `stopping` run still owns the executor. Edit the existing source with local file tools.
3. Call `reload_tasks(task_ids=[...])` with the affected IDs. Omit `task_ids` to reload all registered tasks and plugins. Prefer a selected reload when the change is local; tasks sharing its module and all tasks/pages in its plugin reload together.
4. Poll `get_run_status(run_id)` until terminal. A successful reload returns replacement task descriptors in `result`; inspect `run.log` and `status.json` on failure, fix the source, and retry. A failed reload leaves existing tasks registered, so running them would still test the old code.
5. Restore and verify the target's baseline, then exercise the updated task and assert application-level success. A reload alone does not execute `run()` or prove that automation works.

Reload requests acquire exclusive executor ownership, stopping scheduled one-time tasks and suspending triggers until completion. They do not interact with the target UI, so reset it before the next execution. A queued reload can be cancelled with `stop_task`; once its transaction starts, let it finish. A committed reload reports `succeeded` even if a stop was requested during the transaction.

## Test the registered implementation

Use the actual GUI task card or a thin MCP test harness submitted with `run_task(file_path)`. The harness should call the registered task through `self.get_task_by_class(ExistingTask)`, reuse its recovery/verification methods, and invoke its implementation. Keep changes to task behavior in the existing task module rather than copying that behavior into the harness. The harness must still implement `reset_to_start()`, `verify_start_state()`, and `run()` as described in the development skill.

Calling a registered task method directly does not give that instance the scheduler's enabled/running flags or current-task context. Use the GUI Start action when the implementation depends on that lifecycle, or establish and restore the required context in the harness with `try/finally`. Assert an observable result so an early return cannot masquerade as success.

Debug mode does not automatically reload task files. Python callers can also queue `self.reload_tasks([ExistingTask])` or `self.reload_tasks()`; these run after the current task or debug call returns. Do not wait on that job from executor code or the GUI thread. During an MCP attempt, use the MCP reload tool after the attempt finishes, since the attempt holds exclusive ownership.

Only registered tasks are discovered or replaced. Add genuinely new tasks to the project config and restart the owned runtime to discover them. Task modules reload from current source; plugin helpers reload with their plugin. Helpers outside plugins remain cached: restart the owned runtime when those dependencies change. Preserve local failure evidence before restarting.
