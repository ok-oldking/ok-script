from __future__ import annotations

import asyncio
import dataclasses
import re
import shutil
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from ok.core.events import EventMessage, communicate


LOG_LINE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3}\s+"
    r"(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
)
LOG_LEVELS = {"ALL": 0, "DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


def _copy_web_icon(config, static_dir):
    """Copy the configured application icon into the served web assets."""
    configured = config.get("gui_icon")
    if not configured or str(configured).startswith(":/"):
        return None

    source = Path(configured)
    if not source.is_absolute():
        from ok.util.file import get_path_relative_to_exe
        source = Path(get_path_relative_to_exe(str(configured)))
    if not source.is_file():
        return None

    static_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower() or ".ico"
    destination = static_dir / f"app-icon{suffix}"
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    return f"/static/{destination.name}?version={destination.stat().st_mtime_ns}"


def _json_value(value: Any):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if dataclasses.is_dataclass(value):
        return _json_value(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "shape") and hasattr(value, "dtype"):
        return {
            "type": value.__class__.__name__,
            "shape": list(value.shape),
            "dtype": str(value.dtype),
        }
    if hasattr(value, "name"):
        return {"name": str(value.name), "type": value.__class__.__name__}
    return str(value)


def _task_payload(task):
    return {
        "name": task.name,
        "class_name": task.__class__.__name__,
        "enabled": bool(task.enabled),
        "running": bool(task.running),
        "paused": bool(task.paused),
        "trigger": task in task.executor.trigger_tasks,
        "description": getattr(task, "description", "") or "",
    }


def _method_name(method):
    return method.__name__ if isinstance(method, type) else str(method)


def _device_payload(device, preferred_id):
    kind = str(device.get("device") or "")
    kind_label = {
        "windows": "PC",
        "adb": "Android",
        "browser": "Browser",
    }.get(kind, kind.title() or "Device")
    connected = bool(device.get("connected"))
    state = "Connected" if connected else "Disconnected"
    details = " ".join(str(value) for value in (
        device.get("nick"), device.get("address"), device.get("resolution")
    ) if value)
    return {
        "id": str(device.get("imei") or ""),
        "label": f"{kind_label} {state}: {details}".strip(),
        "kind": kind,
        "connected": connected,
        "resolution": str(device.get("resolution") or ""),
        "selected": device.get("imei") == preferred_id,
        "keywords": " ".join(str(value) for value in (
            device.get("nick"), device.get("exe"), device.get("address"), device.get("full_path")
        ) if value),
    }


def _read_log(path, level="ALL", query="", max_lines=5000):
    """Read and filter the active log without importing the Qt LogWindow."""
    level = level.upper()
    if level not in LOG_LEVELS:
        raise ValueError(f"Unknown log level: {level}")
    if not path.is_file():
        return {"path": str(path), "text": "", "line_count": 0, "modified": None}

    with path.open("rb") as file:
        file.seek(0, 2)
        position = file.tell()
        chunks = []
        line_count = 0
        while position > 0 and line_count <= max_lines * 2:
            size = min(1024 * 1024, position)
            position -= size
            file.seek(position)
            chunk = file.read(size)
            chunks.insert(0, chunk)
            line_count += chunk.count(b"\n")

    lines = b"".join(chunks).decode("utf-8", errors="replace").splitlines()
    records = []
    current = None
    for line in lines:
        match = LOG_LINE_PATTERN.match(line)
        if match or current is None:
            current = {"level": match.group("level") if match else "INFO", "lines": [line]}
            records.append(current)
        else:
            current["lines"].append(line)

    threshold = LOG_LEVELS[level]
    query = query.strip().lower()
    visible = []
    for record in records:
        block = "\n".join(record["lines"])
        if LOG_LEVELS.get(record["level"], 0) < threshold or (query and query not in block.lower()):
            continue
        visible.extend(record["lines"])
    visible = visible[-max_lines:]
    return {
        "path": str(path),
        "text": "\n".join(visible) + ("\n" if visible else ""),
        "line_count": len(visible),
        "modified": path.stat().st_mtime,
    }


class WebRuntime:
    def __init__(self, config, icon_url=None):
        from ok import OK

        web_config = dict(config)
        web_config["use_gui"] = False
        self.ok = OK(web_config)
        # The web controls and the native overlay share persisted state.
        self.ui_config = self.ok.headless_app.ok_config
        self.last_capture_path = None
        self.icon_url = icon_url

    @property
    def executor(self):
        return self.ok.task_executor

    def status(self):
        current = self.executor.current_task
        hotkey = self.executor.basic_options.get("Start/Stop")
        return {
            "paused": bool(self.executor.paused),
            "running": self.executor.thread is not None and self.executor.thread.is_alive(),
            "current_task": current.name if current else None,
            "task_count": len(self.executor.get_all_tasks()),
            "hotkey": hotkey if hotkey and hotkey != "None" else None,
        }

    @property
    def device_manager(self):
        return self.ok.device_manager

    def _capture_methods(self, device):
        if not device:
            return []
        if device.get("device") == "windows":
            configured = (self.device_manager.windows_capture_config or {}).get("capture_method", [])
            methods = configured if isinstance(configured, list) else [configured]
            methods = methods or ["windows"]
        elif device.get("device") == "browser":
            methods = ["browser"]
        elif device.get("emulator") is not None:
            methods = ["adb", "ipc"] if device.get("emulator") else ["adb"]
        else:
            methods = ["adb"]
        selected = self.device_manager.get_preferred_capture()
        return [{
            "id": _method_name(method),
            "label": self.ok.headless_app.tr(_method_name(method)),
            "selected": _method_name(method) == selected,
        } for method in methods if method]

    def _interaction_methods(self, device):
        if not device:
            return []
        kind = device.get("device")
        if kind == "windows":
            configured = (self.device_manager.windows_capture_config or {}).get("interaction", [])
            methods = configured if isinstance(configured, list) else [configured]
            methods = methods or ["Pynput"]
        elif kind == "browser":
            methods = ["BrowserInteraction"]
        elif kind == "adb":
            methods = ["ADBInteraction"]
        else:
            methods = ["Default Interaction"]
        selected = self.device_manager.config.get("interaction")
        return [{
            "id": _method_name(method),
            "label": self.ok.headless_app.tr(_method_name(method)),
            "selected": _method_name(method) == selected or (not selected and index == 0),
        } for index, method in enumerate(methods) if method]

    def capture_ui(self):
        preferred = self.device_manager.get_preferred_device()
        preferred_id = preferred.get("imei") if preferred else None
        return {
            "title": self.ok.config.get("gui_title", "ok-script"),
            "version": self.ok.config.get("version") or "dev",
            "icon_url": self.icon_url,
            "status": self.status(),
            "devices": [_device_payload(device, preferred_id) for device in self.device_manager.get_devices()],
            "capture_methods": self._capture_methods(preferred),
            "interaction_methods": self._interaction_methods(preferred),
            "overlay": {
                "boxes": bool(self.ui_config.get("use_overlay", False)),
                "logs": bool(self.ui_config.get("show_overlay_logs", True)),
            },
        }

    def refresh_devices(self):
        # DeviceManager owns the worker and publishes adb_devices when done.
        return bool(self.device_manager.refresh())

    def start(self):
        return self.ok.start_runtime()

    def select_device(self, device_id):
        if device_id not in {device.get("imei") for device in self.device_manager.get_devices()}:
            raise ValueError(f"Unknown device: {device_id}")
        self.device_manager.set_preferred_device(imei=device_id)
        return self.capture_ui()

    def select_capture(self, method):
        allowed = {item["id"] for item in self._capture_methods(self.device_manager.get_preferred_device())}
        if method not in allowed:
            raise ValueError(f"Unknown capture method: {method}")
        self.device_manager.set_capture(method)
        return self.capture_ui()

    def select_interaction(self, method):
        allowed = {item["id"] for item in self._interaction_methods(self.device_manager.get_preferred_device())}
        if method not in allowed:
            raise ValueError(f"Unknown interaction method: {method}")
        self.device_manager.set_interaction(method)
        return self.capture_ui()

    def set_overlay(self, name, value):
        key = {"boxes": "use_overlay", "logs": "show_overlay_logs"}.get(name)
        if key is None:
            raise ValueError(f"Unknown overlay setting: {name}")
        self.ui_config[key] = bool(value)
        overlay = self.ok.headless_app.get_overlay_view()
        if name == "boxes":
            overlay.set_boxes_enabled(value)
        return self.capture_ui()

    def run_tool(self, action):
        from ok.util.explorer import open_explorer_folder, reveal_in_explorer

        if action == "install-folder":
            open_explorer_folder(Path.cwd())
            return {"message": "Install folder opened", "kind": "folder"}
        if action == "log-folder":
            open_explorer_folder(Path.cwd() / "logs")
            return {"message": "Log folder opened", "kind": "folder"}
        if action == "screenshot-folder":
            folder = Path(getattr(self.ok.screenshot, "screenshot_folder", None) or "screenshots")
            open_explorer_folder(folder)
            return {"message": "Screenshot folder opened", "kind": "folder"}
        if action == "export-logs":
            from ok.util.file import get_downloads_folder
            archive = Path(get_downloads_folder()) / f"{self.ok.config.get('gui_title', 'ok-script')}-log.zip"
            archive.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
                for folder_name in ("screenshots", "logs"):
                    folder = Path.cwd() / folder_name
                    if folder.is_dir():
                        for file_path in folder.rglob("*"):
                            if file_path.is_file():
                                output.write(file_path, file_path.relative_to(Path.cwd()))
            reveal_in_explorer(archive)
            return {"message": f"Logs exported to {archive}", "kind": "export"}
        if action == "capture":
            method = self.device_manager.capture_method
            if method is None:
                raise RuntimeError("No capture method is active")
            frame = method.get_frame()
            if frame is None:
                raise RuntimeError("Could not capture a frame")
            folder = Path(getattr(self.ok.screenshot, "screenshot_folder", None) or "screenshots")
            folder.mkdir(parents=True, exist_ok=True)
            name = "manual_" + datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self.ok.screenshot.generate_screen_shot(
                frame,
                self.ok.screenshot.ui_dict,
                str(folder),
                name,
                True,
                None,
                processor=self.ok.config.get("screenshot_processor"),
            )
            if not path:
                raise RuntimeError("Could not save the captured frame")
            self.last_capture_path = Path(path).resolve()
            return {
                "message": f"Screenshot saved to {self.last_capture_path}",
                "kind": "capture",
                "resource_url": f"/api/capture/image?version={self.last_capture_path.stat().st_mtime_ns}",
            }
        if action == "ocr":
            if self.executor.paused:
                raise RuntimeError("Please start the executor first")
            tasks = self.executor.get_all_tasks()
            if not tasks:
                raise RuntimeError("No task is available for OCR")
            result = tasks[0].ocr(log=True, screenshot=True)
            folder = Path(getattr(self.ok.screenshot, "screenshot_folder", None) or "screenshots").resolve()
            folder.mkdir(parents=True, exist_ok=True)
            if result:
                output = folder / "ocr_result.txt"
                output.write_text(
                    "".join(f"{box.name}, {box}, {box.confidence}\n" for box in result),
                    encoding="utf-8",
                )
            open_explorer_folder(folder)
            return {"message": f"OCR completed: {len(result or [])} result(s)", "kind": "ocr"}
        raise ValueError(f"Unknown tool action: {action}")

    def logs(self, level="ALL", query=""):
        return _read_log(Path.cwd() / "logs" / "ok-script.log", level=level, query=query)

    def tasks(self):
        return [_task_payload(task) for task in self.executor.get_all_tasks()]

    def start_task(self, name):
        task, _is_trigger = self.ok.get_task(name)
        if not self.ok.headless_app.start_controller.do_start(task):
            raise RuntimeError(f"Start task failed: {task.name}")
        return _task_payload(task)

    def pause(self):
        if not self.executor.paused:
            self.executor.pause()
        return self.status()

    def resume(self):
        if not self.ok.headless_app.start_controller.do_start():
            raise RuntimeError("Start failed")
        return self.status()

    def stop_task(self):
        self.executor.stop_current_task()
        return self.status()

    def close(self):
        self.ok.quit()


def create_web_app(config):
    try:
        from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError(
            "The web UI requires FastAPI and Uvicorn. Install ok-script[web]."
        ) from exc

    # FastAPI resolves postponed endpoint annotations from module globals.
    globals()["WebSocket"] = WebSocket

    static_dir = Path(__file__).with_name("static")
    icon_url = _copy_web_icon(config, static_dir)
    runtime = WebRuntime(config, icon_url=icon_url)

    @asynccontextmanager
    async def lifespan(_app):
        runtime.start()
        yield
        await asyncio.to_thread(runtime.close)

    app = FastAPI(title=config.get("gui_title", "ok-script"), lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.state.runtime = runtime

    @app.get("/")
    async def index():
        return FileResponse(static_dir / "index.html")

    @app.get("/api/status")
    async def status():
        return runtime.status()

    @app.get("/api/ui/capture")
    async def capture_ui():
        return runtime.capture_ui()

    @app.post("/api/devices/refresh")
    async def refresh_devices():
        # Completion and state are published through communicate.adb_devices.
        return {"accepted": runtime.refresh_devices()}

    @app.post("/api/devices/select")
    async def select_device(body: dict):
        try:
            return await asyncio.to_thread(runtime.select_device, str(body.get("id", "")))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/capture-methods/select")
    async def select_capture(body: dict):
        try:
            return await asyncio.to_thread(runtime.select_capture, str(body.get("id", "")))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/interaction-methods/select")
    async def select_interaction(body: dict):
        try:
            return await asyncio.to_thread(runtime.select_interaction, str(body.get("id", "")))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/overlay")
    async def set_overlay(body: dict):
        try:
            return runtime.set_overlay(str(body.get("name", "")), bool(body.get("value")))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/tools/{action}")
    async def run_tool(action: str):
        try:
            result = await asyncio.to_thread(runtime.run_tool, action)
            return {"ok": True, **result}
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/capture/image")
    async def capture_image():
        path = runtime.last_capture_path
        if path is None or not path.is_file():
            raise HTTPException(status_code=404, detail="No captured image is available")
        return FileResponse(path)

    @app.get("/api/logs")
    async def logs(level: str = "ALL", query: str = ""):
        try:
            return await asyncio.to_thread(runtime.logs, level, query)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/tasks")
    async def tasks():
        return runtime.tasks()

    @app.post("/api/tasks/{name}/start")
    async def start_task(name: str):
        try:
            return await asyncio.to_thread(runtime.start_task, name)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/executor/pause")
    async def pause():
        return runtime.pause()

    @app.post("/api/executor/resume")
    async def resume():
        try:
            return await asyncio.to_thread(runtime.resume)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/executor/stop-task")
    async def stop_task():
        return runtime.stop_task()

    @app.websocket("/api/events")
    async def events(websocket: WebSocket):
        await websocket.accept()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[EventMessage] = asyncio.Queue(maxsize=200)

        def receive(message):
            def enqueue():
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(message)
            loop.call_soon_threadsafe(enqueue)

        communicate.any.connect(receive)
        try:
            while True:
                message = await queue.get()
                payload = {
                    "event": message.name,
                    "args": _json_value(message.args),
                    "kwargs": _json_value(message.kwargs),
                }
                if message.name in {
                    "adb_devices", "executor_paused", "starting_emulator",
                    "task", "task_list_updated",
                }:
                    payload["ui"] = await asyncio.to_thread(runtime.capture_ui)
                await websocket.send_json(payload)
        except WebSocketDisconnect:
            pass
        finally:
            communicate.any.disconnect(receive)

    return app
