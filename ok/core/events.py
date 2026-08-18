"""Thread-safe, framework-neutral application events.

The public ``communicate`` object intentionally keeps the old ``signal.emit`` /
``signal.connect`` shape.  Core code can therefore publish events without
importing Qt, while desktop and web adapters subscribe to the same bus.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any


_dispatcher: Callable[[Callable[..., Any], tuple[Any, ...], dict[str, Any]], None] | None = None


def set_event_dispatcher(dispatcher=None) -> None:
    """Install a UI scheduler, or restore synchronous headless dispatch."""
    global _dispatcher
    _dispatcher = dispatcher


class EventSignal:
    def __init__(self, name: str, on_emit=None):
        self.name = name
        self._on_emit = on_emit
        self._subscribers: list[Callable[..., Any]] = []
        self._lock = threading.RLock()

    def connect(self, callback: Callable[..., Any]) -> Callable[..., Any]:
        if not callable(callback):
            raise TypeError(f"Subscriber for {self.name!r} must be callable")
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)
        return callback

    def disconnect(self, callback: Callable[..., Any] | None = None) -> None:
        with self._lock:
            if callback is None:
                self._subscribers.clear()
            elif callback in self._subscribers:
                self._subscribers.remove(callback)

    def emit(self, *args: Any, **kwargs: Any) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers)
        for callback in subscribers:
            if _dispatcher is None:
                callback(*args, **kwargs)
            else:
                _dispatcher(callback, args, kwargs)
        if self._on_emit is not None:
            self._on_emit(*args, **kwargs)

    @contextmanager
    def subscribed(self, callback: Callable[..., Any]):
        self.connect(callback)
        try:
            yield callback
        finally:
            self.disconnect(callback)


@dataclass(frozen=True)
class EventMessage:
    name: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


class EventBus:
    _event_names = (
        "log", "fps", "frame_time", "scene", "draw_box", "clear_box",
        "task", "task_list_updated", "task_done", "window",
        "loading_progress", "notification", "executor_paused", "screenshot",
        "blur_overlay", "clear_blur_overlay", "adb_devices",
        "config_validation", "tab", "capture_error", "starting_emulator",
        "quit", "start_success", "act", "copyright", "global_config",
        "restart_admin", "task_tab",
    )

    def __init__(self):
        self.any = EventSignal("*")
        for name in self._event_names:
            signal = EventSignal(name, self._forward(name))
            setattr(self, name, signal)

    def _forward(self, name: str):
        def forward(*args: Any, **kwargs: Any) -> None:
            self.any.emit(EventMessage(name, args, kwargs))
        return forward

    def emit_draw_box(self, key=None, boxes=None, color=None, frame=None, debug=True):
        self.draw_box.emit(key, boxes, color, frame, debug)


communicate = EventBus()
