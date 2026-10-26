# Local MCP task development

The optional MCP server lets a local coding agent run Python task files against
an existing ok-script project. The agent writes and edits files, starts the
process, and reads local logs and images with its own filesystem tools.

## Install and start

Install the MCP profile alongside the capture and OCR profiles your project uses.
Use the project's virtual environment when one exists:

```powershell
.\.venv\Scripts\python.exe -m pip install "ok-script[default,mcp]"
.\.venv\Scripts\python.exe -m ok mcp --config src.config:config
```

Use the application's existing requirements or lockfile when available and keep
its chosen ok-script version. OpenCV remains a separate installation chosen by
the application.

The default URL is `http://127.0.0.1:8765/mcp`. Use `--port 8766` to change it,
or `--port 0` to choose an available port. The process stays running between
attempts. Its regular task scheduler stays paused in this headless mode.

Starting a GUI for the same project replaces its registered console instance
and closes that instance's MCP server. Use separate GUI and development entry
points when the user-facing GUI should have MCP disabled. Close the GUI before
starting another console development session.

To enable the same tools in the desktop application:

```powershell
.\.venv\Scripts\python.exe -m ok gui --config src.config:config --mcp
```

Applications using `OK(config).start()` can enable MCP through their config:

```python
"mcp": {"enabled": True, "port": 8765, "artifact_directory": "logs/mcp"}
```

The server binds only to IPv4 loopback and validates HTTP Host and Origin.
Read `logs/mcp/connection.json` for the URL, bearer token and process ID after
startup. Configure the agent's MCP client with that URL and the HTTP header
`Authorization: Bearer <token>`. Set the environment variable
`OK_SCRIPT_MCP_TOKEN` before starting the process if you need a stable token;
otherwise a new token is generated on each startup. Treat this token as local
developer access: task files execute Python with the process's permissions.

## Skill discovery

All exposed skills are for third-party applications using the library or MCP:
application setup, task development and reloading, template assets, tests, and
environment selection. They ship in the pip package with their supporting files
and this guide. No library source checkout is needed. Skills discovered from a
checkout and an installed release have the same consumer scope.

Call `list_skills()` for IDs, names, descriptions, resource URIs and absolute
`SKILL.md` paths, then `get_skill(skill_id)` to read the relevant instructions.
For example, use `get_skill("develop")` before implementing tasks. Relative
links resolve from the returned local path. Repository commit, package release,
and library translation maintenance are not exposed as skills or resources.

Clients supporting MCP resources can also discover these skills through
`resources/list` and read `ok-script://skills/<skill_id>` through
`resources/read`. Both interfaces return the same instructions.

## Tools

| Tool | Arguments | Result |
| --- | --- | --- |
| `list_skills` | None | Available skill IDs, names, descriptions, URIs and local paths. |
| `get_skill` | `skill_id` | Skill metadata and full Markdown content. |
| `list_tasks` | None | Registered task IDs, names, absolute source paths, types and plugin ownership. |
| `reload_tasks` | Optional `task_ids` list | Immediately returns a run ID for reloading selected registered tasks, or all tasks/plugins when omitted. |
| `run_task` | `file_path` | Immediately returns a run ID, source hash and absolute artifact paths. |
| `get_run_status` | `run_id` | Execution state, phase, brief error and artifact paths. |
| `stop_task` | `run_id` | Requests cancellation and returns the current state. |
| `screenshot` | None | Saves the target image and returns its absolute path, dimensions, capture timestamp and `cached` flag. |

States are `queued`, `running`, `stopping`, `succeeded`, `failed`, and
`cancelled`. Only the last three are terminal. Run IDs are scoped to the current
process; saved artifacts remain available after restarting it.

## Preferred workflow for existing tasks

Read the `reload-tasks` skill through `get_skill("reload-tasks")`. Use
`list_tasks()` to find the existing implementation and its absolute source path,
edit that file locally, then call:

```python
reload_tasks(task_ids=["src.tasks.ExistingTask.ExistingTask"])
reload_tasks()  # All registered tasks and plugins
```

Use the exact `task_id` returned by `list_tasks`; display names and bare class
names are not IDs. An empty list selects no tasks. Poll `get_run_status(run_id)`
until the reload succeeds before testing. The record's `operation` is
`reload_tasks`, and its `result` contains descriptors for the replacement tasks.
Reload failures include an error and local `run.log`/`status.json` paths; existing
task instances remain registered. A failure means subsequent execution would
still use the old implementation.

Reloads compile the current task source without timestamp-based bytecode caches.
Tasks sharing a module reload together; selecting any plugin task reloads its
entire plugin, including pages and helper modules. Unselected task modules and
helpers outside plugins stay cached. Restart the owned runtime after changing
those helpers or adding new task registrations to the config. Debug mode does
not watch or reload task files automatically.

Reloading does not call the automation's `run()`, reset the target application,
or demonstrate success. Restore and verify the baseline before testing through
the actual GUI task card or a thin `run_task` harness that calls the registered
implementation with `self.get_task_by_class(ExistingTask)`. Keep behavior changes
in the existing task source instead of copying it into a temporary task.

File runs and reloads share the same active-run slot and exclusive executor
ownership. Wait for the previous run and cleanup to finish before reloading.
Reload requests stop scheduled one-time tasks and suspend triggers until
completion; they do not restart stopped one-time tasks. `stop_task` can cancel a
queued reload. Once the reload transaction starts, it finishes atomically; a
successful commit reports `succeeded` even if a stop was requested meanwhile.

## Execution ownership

Only one task file runs at a time. Each attempt acquires exclusive executor
ownership: existing one-time tasks are stopped, and triggers are suspended until
the attempt finishes. Stopped one-time tasks are not restarted automatically.

Cancellation is cooperative at framework sleep, capture and wait checks. A run
marked `stopping` still owns the executor, including during cleanup. Code stuck
in a blocking library or a Python loop without checks may require restarting
the process. Wait for it to stop or exit before starting another process against
the same application.

When idle, `screenshot` requests a fresh frame on the executor thread. During
execution it saves the latest independent frame snapshot, without touching the
capture backend from a second thread. Inspect `cached` and `captured_at` to
judge freshness. Before the first captured frame it reports that no image is
available. A task can call `self.executor.next_frame()` to update observations.

## Task file contract

Each file defines a synchronous `class Task(BaseTask)` with these methods:

1. `reset_to_start()` restores the application baseline. Reuse an existing
   recovery function when available. Make it safe to call when already at the
   baseline and after a partially completed attempt.
2. `verify_start_state()` asserts the observable starting conditions or returns
   `True`. Returning `False`, another value, or raising blocks the main task.
   Returning `None` is supported for checks expressed as assertions.
3. `run()` performs the automation and asserts its success conditions. Returning
   `False` or raising marks the attempt as failed.

The runner creates a fresh instance, calls `after_init()` and `post_init()`,
prepares capture and interaction, then runs reset, verification and the task.
It calls `on_destroy()` even if initialization, recovery or execution fails
after constructing the task. Cleanup finishes before ownership is released.
`succeeded` means the code completed without failure; include application-level
success checks in `run()`.

See the bundled [examples/mcp_observe.py](../examples/mcp_observe.py) for a runnable example. It captures
the configured target without changing its state, so its reset is a no-op.
For an interactive task, replace that recovery method and starting-state check.

Task code has the normal BaseTask API. For example, import an existing task's
class and call `self.get_task_by_class(ExistingTask).some_method()` to reuse its
functions. Registered project tasks are already available through the executor.
Unregistered task classes need to be instantiated and initialized by your code.

Each invocation compiles the current task file directly, including same-size
edits made within one second. Project imports and sibling imports are supported;
use absolute imports for project packages. Shared imported modules remain cached
in Python: restart the process after changing those dependencies. Task instances
are temporary and do not appear in the regular task list.

## Local evidence and the iteration loop

Each attempt writes `logs/mcp/<run_id>/run.log` and `status.json`. The run log
captures executor-thread stdout, stderr, ok-script logging and the failure
traceback. Background-thread messages remain in the application's normal logs.
`self.artifact_directory` is a `Path` for additional per-attempt files.

Write useful diagnostics in the task itself:

```python
self.log_info("Opening settings")
self.screenshot("before_settings")
# Perform actions, inspect the resulting UI, and assert the expected outcome.
```

Task screenshots use the project's normal screenshot directory and naming.
They are saved asynchronously by the normal screenshot worker. The MCP
`screenshot` tool returns only after its observation image has been saved under
`logs/mcp/observations/`.

For existing tasks, the agent's loop is: discover the registered source, edit it,
reload its task ID, wait for success, then run the registered implementation
through a thin harness or the GUI and inspect local evidence. For new tasks,
iterate on the submitted file before registering it in the project. Reset and
starting-state verification run before every attempt, including the first one.
Preserve failure evidence before the next reset. No MCP tools are needed for
file editing, log reading, or process management.
