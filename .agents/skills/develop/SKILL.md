---
name: develop
description: Implement and debug third-party application tasks with the ok-script library or MCP server, preferring in-place task edits and reloads with verified target recovery.
---

# Develop

Use this skill inside the consuming application's project. Edit its task modules, configuration, and assets through the installed ok-script APIs and local MCP server. Developing or changing the ok-script library itself is outside this skill's scope.

Read [docs/mcp.md](../../../docs/mcp.md) for the current server, tools, task contract, and artifacts. The coding agent already has local file and process access: write code and read logs/images directly. Use [setup-env](../setup-env/SKILL.md) or [setup-project](../setup-project/SKILL.md) only when setup is missing.

For screenshot annotations and named template features, use [generate-templates](../generate-templates/SKILL.md): retain originals in `ok_templates`, update its COCO annotations, generate runtime assets with the existing exporter, and verify `find_feature`/`find_one` against those assets.

For existing registered tasks, prefer [reload-tasks](../reload-tasks/SKILL.md): discover their source with `list_tasks()`, edit it in place, call `reload_tasks(task_ids=[...])`, and wait for a successful reload before testing. Keep automation behavior in its existing module; use temporary MCP files only as thin validation harnesses. Create new task implementations when the requested functionality is new.

## Connect to the local runtime

Use the project's venv and existing development launcher. Without a custom launcher, start `python -m ok mcp --config <module>:<config>` through that interpreter from the project directory. Keep it running between attempts. The agent can start this process itself; launch background console helpers hidden on Windows.

Read the configured artifact directory's `connection.json` (normally `logs/mcp/connection.json`) for URL, bearer token, and PID. Check that PID and listener are live; the file can outlast its server. Connect with the supplied URL and `Authorization: Bearer <token>` header. Keep tokens out of normal output. Use a native MCP connection when available, or the installed official SDK and a local client script when it is not.

The tools are `list_tasks()`, `reload_tasks(task_ids=None)`, `run_task(file_path)`, `get_run_status(run_id)`, `stop_task(run_id)`, and `screenshot()`. Reloads return run IDs tracked by the same status and stop tools. Pass an absolute path to `run_task`; keep task logic in files. Read logs and edit files locally rather than adding inline-code, file-editing, or log-reading tools.

## Define recovery and success before iterating

For MCP execution, define a synchronous `class Task(BaseTask)` in the submitted file. For an existing task, make this a thin harness that delegates to its registered instance. Implement:

- `reset_to_start()`: restore the application's baseline before every attempt, including the first. Reuse an existing recovery function when available, or write one. Handle partially completed actions and blocking modal dialogs; make repeated resets safe.
- `verify_start_state()`: check observable baseline conditions with assertions or return `True`. A failed verification must prevent the main actions.
- `run()`: perform the automation and assert application-level success. Completing Python execution alone does not prove success.

Use existing task functions through `self.get_task_by_class(ExistingTask)` when that class is registered. A capture/scene cache reset such as `reset_scene()` does not undo application actions. Use a no-op application reset only when the task makes no state changes. Keep construction and discovery lightweight: the GUI discovers tasks before its executor starts, so avoid executor-dependent sleep/capture or interactive recovery in `on_create()`.

Prefer visual geometry, color classification, and template matching for regular controls and small digits. Use OCR when the target requires it, rather than introducing it by default. Inspect captured pixels, coordinate scaling, and UI timing before changing recognition thresholds. Verify decisions from visible UI; do not substitute hidden application state or process memory for a requested visual algorithm.

## Run, observe, modify

1. Establish working capture and input on the real target. Prioritize PostMessage for background interaction and verify actual effects; a successful API call does not establish that the target reacted.
2. Put milestone logs, screenshots, bounded waits, and assertions in task code. MCP provides `self.artifact_directory` for per-attempt results; normal task screenshots use the configured screenshot folder. Save evidence around failures before resetting.
3. Submit the task path with `run_task`. Poll `get_run_status` until `succeeded`, `failed`, or `cancelled`. Inspect local `run.log`, `status.json`, task output, and screenshots. Background-thread logs may be in the application's normal log files.
4. Use `screenshot()` for additional observations. It captures fresh frames when idle; while a task runs it saves the latest cached frame. Inspect `captured_at` and `cached`. Before the first captured frame there may be no image. Capture again through task code when fresh evidence is needed; normal task screenshots can finish writing asynchronously.
5. Fix the evidenced cause in the existing registered task's source, reload its ID through MCP, and wait for success before resubmitting the validation harness. The runner also reloads the submitted harness file on each invocation. Registered task modules and plugin helpers refresh through `reload_tasks`; helpers outside plugins remain cached and require restarting the owned runtime after edits. Do not infer that a failed reload tested the updated code.
6. Continue through the requested success condition, checking repeat runs and relevant target variations. Bound in-task retries and preserve why an attempt failed; do not retry irreversible actions beyond the user's authorization.

Only one attempt owns the executor. Cancellation is cooperative: `stopping` is not terminal, and a client timeout is not proof that execution stopped. Wait for the task and cleanup to finish before resetting or submitting again. If blocked code requires restarting the runtime, terminate only the verified owned process and wait for its exit before restarting against the same target.

## Make the task usable from the GUI

When the task is also a user feature, register it in `onetime_tasks` and set a useful task name and description. File submissions alone do not populate the GUI list.

The MCP runner invokes reset/verification and supplies an artifact directory. The normal GUI scheduler calls `run()` without those MCP hooks. Support both paths: let GUI execution prepare recovery, verification, and a fresh local artifact directory; honor MCP's already verified start and provided directory. Clear per-attempt flags in `finally`, and refresh settings, timers, results, and artifact paths for repeated GUI runs. Keep recovery in the executor execution path, not GUI construction.

Use the separate MCP-disabled GUI launcher with `pythonw.exe` and test the actual task card's Start action. Check that starting the user GUI replaces the same project's console runtime and closes its MCP listener. A passing file submission alone does not verify GUI lifecycle behavior.

Report the task/config paths, tested target states or sizes, observed success evidence, relevant checks, and remaining limits. Extend existing tests for meaningful recognition, recovery, or lifecycle changes; use real target execution to verify input and capture behavior.
