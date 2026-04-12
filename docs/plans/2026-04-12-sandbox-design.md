# Custom Script Sandbox Design

Date: 2026-04-12
Status: Approved

## Problem

Custom scripts loaded from `ok_tasks/` and `ok_import/` run in the host process with full privileges via `importlib.exec_module()`. A malicious script can execute arbitrary OS commands, access the filesystem, exfiltrate data, or crash the host application.

## Threat Model

Scripts may come from untrusted third parties (shared online, community sources). Primary threats: file system access, network calls, process spawning, data exfiltration, host crash via unhandled exceptions.

## Approach

**`multiprocessing.Queue` + `shared_memory`** — a persistent sandbox process with a `ProxyExecutor` that mirrors the `TaskExecutor` API. Each method call is serialized as an IPC message to the main process, which executes the real operation and returns the result.

Built-in developer tasks run unchanged in the host process. Only custom and imported scripts are sandboxed.

## Architecture

```
Main Process                                Sandbox Process (persistent)
┌──────────────────────────┐                ┌────────────────────────────┐
│ TaskExecutor             │   request      │ ProxyExecutor              │
│   ├─ IPCThread ──────────┼───────────────►│   ├─ mirrors 42 methods    │
│   │  reads queue         │   response     │   ├─ serializes to queue   │
│   │  executes ops        │◄───────────────┤   └─ returns to task       │
│   └─ frame writer        │                │                            │
│      writes to shm       │──── shm ──────►│ Frame reader from shm      │
│                          │                │   └─ numpy array view      │
│ Built-in tasks run       │                │ User Task (BaseTask)       │
│ unchanged in-process     │                │   restricted __builtins__  │
└──────────────────────────┘                └────────────────────────────┘
```

### New Files

| File | Purpose |
|---|---|
| `ok/sandbox/__init__.py` | Package marker |
| `ok/sandbox/proxy_executor.py` | Mirrors ~42 TaskExecutor methods, each serialized to IPC message |
| `ok/sandbox/sandbox_runner.py` | Manages sandbox process lifecycle: spawn, heartbeat, restart, shutdown |
| `ok/sandbox/ipc_protocol.py` | Message types, Box/Feature serialization, request/response protocol |

### Modified Files

| File | Change |
|---|---|
| `ok/gui/tasks/TaskManger.py` | `load_user_tasks()` and `load_imported_tasks()` route through `SandboxRunner` |
| `ok/feature/Box.py` | Add `to_dict()` / `from_dict()` serialization methods |

## IPC Protocol

### Message Format

Every message is a pickled dict via `multiprocessing.Queue`:

```python
{
    "id": "uuid4-string",         # correlation ID
    "type": "request|response|event",
    "op": "click|frame|ocr|...",  # operation name
    "kwargs": { ... },            # arguments (JSON-serializable)
    "result": ...,                # response payload
    "error": "..." | None,        # exception message if failed
}
```

### Two Queues

| Queue | Direction | Purpose |
|---|---|---|
| `request_queue` | Sandbox -> Main | Action requests (click, ocr, get_frame, etc.) |
| `response_queue` | Main -> Sandbox | Responses + host-initiated commands (run, stop, load_script, shutdown) |

### Serialization

- **Box**: `to_dict()` / `from_dict()` with fields x, y, width, height, name, confidence
- **Frames (numpy)**: shared_memory buffer, metadata (height, width, channels) on Queue
- **Feature**: not passed to user code; stays internal to main process

### Operation Catalog

| Category | Operations | Return |
|---|---|---|
| Input | click, mouse_down, mouse_up, swipe, scroll, send_key, send_key_down, send_key_up, input_text, move, back | bool or None |
| Capture | get_frame, get_frame_size | numpy array via shm |
| Feature | find_feature, get_box_by_name, get_feature_by_name, feature_exists | List[Box] / Box / bool |
| OCR | ocr | List[Box] |
| Lifecycle | sleep, wait_condition, wait_scene, reset_scene | bool / result |
| Config | get_global_config, get_config | value |
| Device | is_adb, is_browser, ensure_in_front, adb_shell, adb_ui_dump | various |
| Task | get_task_by_class, run_task_by_class | result |
| GUI | emit_draw_box, emit_screenshot, emit_notification | None |

### Host Commands (Main -> Sandbox)

| Command | Purpose |
|---|---|
| `run` | Execute task's run() method |
| `trigger` | Execute task's trigger() method |
| `enable` | Call task.enable() |
| `disable` | Call task.disable() |
| `load_script` | Load a new .py file into sandbox |
| `unload_script` | Remove a loaded script |
| `shutdown` | Clean exit of sandbox process |

## Security Measures

### Layer 1: Process Isolation

- `multiprocessing` with `spawn` (Windows default) creates separate OS process
- No shared memory except explicit frame shm
- Sandbox has no access to Qt event loop, GUI, or host sys.modules
- Heartbeat monitors sandbox health

### Layer 2: Restricted `__builtins__`

Before loading user code, `SandboxChild` replaces builtins with a whitelist:

**Allowed**: print, len, range, int, float, str, bool, list, dict, tuple, set, bytes, type, isinstance, issubclass, hasattr, getattr, setattr, super, object, Exception subclasses, re, math, time, threading, abs, min, max, sum, sorted, enumerate, zip, map, filter, any, all, round, pow

**Blocked imports**: os, subprocess, socket, http, urllib, requests, ctypes, winreg, shutil, pathlib, signal, multiprocessing, pickle, shelve, marshal, importlib, sys, builtins

A custom `restricted_import()` replaces `__import__` and rejects blocked modules. A `restricted_open()` allows only read access to the script's own directory.

### Layer 3: Heartbeat + Resource Monitoring

- Main process pings every 2 seconds
- Sandbox must respond within 5 seconds
- No response: kill + restart sandbox, reload tasks in disabled state
- GUI notification on restart

### Blocked Attack Vectors

| Attack | Blocked by |
|---|---|
| os.system('...') | Restricted __import__, no os |
| subprocess.Popen(...) | Restricted __import__, no subprocess |
| open('/path', 'w') | restricted_open |
| ctypes memory manipulation | Restricted __import__, no ctypes |
| Infinite loop DoS | Heartbeat timeout, process kill |
| exec()/eval() re-escape | Removed from __builtins__ |
| sys.modules tampering | sys in blocked imports |
| Network exfiltration | socket, http, urllib, requests blocked |

## Error Handling

### Sandbox Crash

Heartbeat timeout -> kill process -> spawn fresh sandbox -> reload tasks in disabled state -> GUI notification.

### Task Exception

Caught by SandboxChild -> error response -> logged and shown in GUI -> sandbox stays alive.

### IPC Timeout

30s response timeout -> TimeoutError -> task marked failed.

### Main Shutdown

Send shutdown command -> wait 3s -> force terminate -> unlink shared_memory.

### Script Load Failure

SyntaxError/ImportError/not BaseTask -> error response -> added to task_errors -> file watcher auto-retries on save.

## Implementation Phases

1. IPC Protocol + Serialization (ipc_protocol.py, Box.to_dict/from_dict)
2. ProxyExecutor (proxy_executor.py)
3. SandboxChild entry point (sandbox_runner.py)
4. SandboxRunner + IPCThread (sandbox_runner.py)
5. TaskManager integration (TaskManger.py)
