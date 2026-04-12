"""Sandbox process management: child entry point and host runner."""
import ast
import builtins
import importlib
import importlib.util
import os
import sys
import time
import traceback
from multiprocessing import Process, Queue, shared_memory

from ok.sandbox.ipc_protocol import (
    IPCMessage, CMD_RUN, CMD_TRIGGER, CMD_ENABLE, CMD_DISABLE,
    CMD_LOAD_SCRIPT, CMD_UNLOAD_SCRIPT, CMD_SHUTDOWN,
)

# --- Security: Builtin Restriction ---

BLOCKED_IMPORTS = frozenset({
    "os", "subprocess", "socket", "http", "urllib", "requests",
    "ctypes", "winreg", "shutil", "pathlib", "signal",
    "multiprocessing", "pickle", "shelve", "marshal",
    "importlib", "sys", "builtins",
})

SAFE_BUILTINS = frozenset({
    "print", "len", "range", "int", "float", "str", "bool", "list", "dict",
    "tuple", "set", "frozenset", "bytes", "bytearray", "type", "isinstance",
    "issubclass", "hasattr", "getattr", "setattr", "delattr", "property",
    "super", "object", "Exception", "ValueError", "TypeError", "KeyError",
    "IndexError", "AttributeError", "RuntimeError", "StopIteration",
    "NotImplementedError", "ZeroDivisionError", "OverflowError",
    "abs", "min", "max", "sum", "sorted", "reversed", "enumerate",
    "zip", "map", "filter", "any", "all", "round", "pow", "divmod",
    "chr", "ord", "hex", "oct", "bin", "id", "hash", "repr", "format",
    "True", "False", "None", "NotImplemented", "Ellipsis",
    "__name__", "__doc__",
})

_original_import = builtins.__import__


def _restricted_import(name, *args, **kwargs):
    root = name.split(".")[0]
    if root in BLOCKED_IMPORTS:
        raise ImportError(f"Import '{name}' is not allowed in custom scripts")
    return _original_import(name, *args, **kwargs)


def create_restricted_builtins():
    """Create a restricted builtins dict for sandbox execution."""
    safe = {}
    for name in SAFE_BUILTINS:
        if hasattr(builtins, name):
            safe[name] = getattr(builtins, name)
    safe["__import__"] = _restricted_import
    return safe


# --- Sandbox Child Process ---

def sandbox_main(request_queue, response_queue, shm_name, shm_size, task_folder):
    """
    Entry point for the sandbox child process.
    Sets up restrictions, creates ProxyExecutor, loads user scripts.
    """
    from ok.sandbox.proxy_executor import ProxyExecutor
    from ok.feature.Box import Box

    executor = ProxyExecutor(request_queue, response_queue, shm_name, shm_size)

    # Track loaded tasks: {task_id: task_info}
    tasks = {}

    def load_script(file_path, task_id=None):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source, filename=file_path)
            classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
            if not classes:
                return None, "No class definitions found"

            module_name = os.path.splitext(os.path.basename(file_path))[0]
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            for cls_name in classes:
                cls_obj = getattr(module, cls_name, None)
                if cls_obj and isinstance(cls_obj, type):
                    # Check if it's a task class by looking for 'run' method
                    if hasattr(cls_obj, 'run') or hasattr(cls_obj, 'trigger'):
                        tid = task_id or f"{module_name}.{cls_name}"
                        try:
                            instance = cls_obj(executor=executor)
                        except TypeError:
                            try:
                                instance = cls_obj(executor)
                            except Exception:
                                instance = cls_obj()
                        instance._sandbox_task_id = tid
                        tasks[tid] = {
                            "instance": instance,
                            "file_path": file_path,
                            "class_name": cls_name,
                        }
                        return tid, None

            return None, "No task class found"
        except Exception as e:
            return None, traceback.format_exc()

    # Load initial scripts if task_folder exists
    if task_folder and os.path.exists(task_folder):
        for f in os.listdir(task_folder):
            if f.endswith(".py"):
                load_script(os.path.join(task_folder, f))

    # Main command loop
    while True:
        try:
            cmd_dict = response_queue.get(timeout=2)
            cmd = IPCMessage.from_dict(cmd_dict)
        except Exception:
            continue

        if cmd.op == CMD_SHUTDOWN:
            break
        elif cmd.op == CMD_LOAD_SCRIPT:
            tid, err = load_script(cmd.kwargs["file_path"], cmd.kwargs.get("task_id"))
            resp = IPCMessage.response(cmd.id, cmd.op,
                                       result=tid if tid else None,
                                       error=err)
            request_queue.put(resp.to_dict())
        elif cmd.op == CMD_UNLOAD_SCRIPT:
            tasks.pop(cmd.kwargs.get("task_id"), None)
            resp = IPCMessage.response(cmd.id, cmd.op, result=True)
            request_queue.put(resp.to_dict())
        elif cmd.op == CMD_RUN:
            tid = cmd.kwargs.get("task_id")
            task_info = tasks.get(tid)
            if task_info:
                try:
                    task_info["instance"].run()
                    resp = IPCMessage.response(cmd.id, cmd.op, result=True)
                except Exception:
                    resp = IPCMessage.response(cmd.id, cmd.op,
                                               error=traceback.format_exc())
                request_queue.put(resp.to_dict())
            else:
                resp = IPCMessage.response(cmd.id, cmd.op, error=f"Task {tid} not found")
                request_queue.put(resp.to_dict())
        elif cmd.op == CMD_TRIGGER:
            tid = cmd.kwargs.get("task_id")
            task_info = tasks.get(tid)
            if task_info:
                try:
                    result = task_info["instance"].trigger()
                    resp = IPCMessage.response(cmd.id, cmd.op, result=result)
                except Exception:
                    resp = IPCMessage.response(cmd.id, cmd.op,
                                               error=traceback.format_exc())
                request_queue.put(resp.to_dict())
        elif cmd.op == CMD_ENABLE:
            tid = cmd.kwargs.get("task_id")
            task_info = tasks.get(tid)
            if task_info and hasattr(task_info["instance"], "enable"):
                task_info["instance"].enable()
                resp = IPCMessage.response(cmd.id, cmd.op, result=True)
                request_queue.put(resp.to_dict())
        elif cmd.op == CMD_DISABLE:
            tid = cmd.kwargs.get("task_id")
            task_info = tasks.get(tid)
            if task_info and hasattr(task_info["instance"], "disable"):
                task_info["instance"].disable()
                resp = IPCMessage.response(cmd.id, cmd.op, result=True)
                request_queue.put(resp.to_dict())


# --- Host-side SandboxRunner ---

class SandboxRunner:
    """Host-side manager for the sandbox process."""

    def __init__(self, task_executor, task_folder=None):
        self.task_executor = task_executor
        self.task_folder = task_folder
        self._process = None
        self._request_queue = None
        self._response_queue = None
        self._shm = None
        self._shm_name = None
        self._shm_size = 1920 * 1080 * 3
        self._ipc_thread = None
        self._running = False

    def spawn(self):
        """Start the sandbox child process."""
        self._request_queue = Queue()
        self._response_queue = Queue()
        try:
            self._shm = shared_memory.SharedMemory(
                name=f"ok_sandbox_{os.getpid()}",
                create=True,
                size=self._shm_size,
            )
            self._shm_name = self._shm.name
        except Exception:
            self._shm = None
            self._shm_name = None

        self._process = Process(
            target=sandbox_main,
            args=(self._request_queue, self._response_queue,
                  self._shm_name, self._shm_size, self.task_folder),
            daemon=True,
        )
        self._process.start()

    def load_script(self, file_path, task_id=None):
        """Load a script into the sandbox."""
        cmd = IPCMessage.command(CMD_LOAD_SCRIPT,
                                 file_path=file_path, task_id=task_id)
        self._response_queue.put(cmd.to_dict())
        resp_dict = self._request_queue.get(timeout=10)
        resp = IPCMessage.from_dict(resp_dict)
        return resp.result, resp.error

    def run_task(self, task_id):
        """Run a task in the sandbox."""
        cmd = IPCMessage.command(CMD_RUN, task_id=task_id)
        self._response_queue.put(cmd.to_dict())
        resp_dict = self._request_queue.get(timeout=300)
        resp = IPCMessage.from_dict(resp_dict)
        return resp.result, resp.error

    def enable_task(self, task_id):
        cmd = IPCMessage.command(CMD_ENABLE, task_id=task_id)
        self._response_queue.put(cmd.to_dict())

    def disable_task(self, task_id):
        cmd = IPCMessage.command(CMD_DISABLE, task_id=task_id)
        self._response_queue.put(cmd.to_dict())

    def shutdown(self):
        """Gracefully shut down the sandbox process."""
        self._running = False
        if self._process and self._process.is_alive():
            cmd = IPCMessage.command(CMD_SHUTDOWN)
            self._response_queue.put(cmd.to_dict())
            self._process.join(timeout=3)
            if self._process.is_alive():
                self._process.terminate()
        if self._shm:
            self._shm.close()
            self._shm.unlink()
