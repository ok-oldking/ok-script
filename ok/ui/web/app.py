from __future__ import annotations

import asyncio
import dataclasses
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from ok.core.events import EventMessage, communicate


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


class WebRuntime:
    def __init__(self, config):
        from ok import OK

        web_config = dict(config)
        web_config["use_gui"] = False
        self.ok = OK(web_config)

    @property
    def executor(self):
        return self.ok.task_executor

    def status(self):
        current = self.executor.current_task
        return {
            "paused": bool(self.executor.paused),
            "running": self.executor.thread is not None and self.executor.thread.is_alive(),
            "current_task": current.name if current else None,
            "task_count": len(self.executor.get_all_tasks()),
        }

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
        self.executor.start()
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

    runtime = WebRuntime(config)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        await asyncio.to_thread(runtime.close)

    app = FastAPI(title=config.get("gui_title", "ok-script"), lifespan=lifespan)
    static_dir = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.state.runtime = runtime

    @app.get("/")
    async def index():
        return FileResponse(static_dir / "index.html")

    @app.get("/api/status")
    async def status():
        return runtime.status()

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
        return runtime.resume()

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
                await websocket.send_json({
                    "event": message.name,
                    "args": _json_value(message.args),
                    "kwargs": _json_value(message.kwargs),
                })
        except WebSocketDisconnect:
            pass
        finally:
            communicate.any.disconnect(receive)

    return app
