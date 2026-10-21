"""Notify imported plugin tasks once per Qt window and live task instance."""

import weakref

from PySide6.QtCore import QObject, QTimer, Slot
from shiboken6 import isValid

from ok import Logger, og
from ok.core.events import communicate

logger = Logger.get_logger(__name__)


class PluginWindowHooks(QObject):
    def __init__(self, window):
        super().__init__(window)
        self._window = weakref.ref(window)
        self._delivered = {}
        self._dispatching = False
        self._closed = [False]
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dispatch)

        # App installs the existing Qt event dispatcher before loading tasks.
        # Only defer/coalesce here; do not add a second cross-thread bridge.
        event = communicate.task_list_updated
        callback = self._schedule
        closed = self._closed

        def dispose(*_args):
            closed[0] = True
            event.disconnect(callback)

        event.connect(callback)
        self.destroyed.connect(dispose)

    @Slot()
    def _schedule(self):
        if not self._closed[0] and not self._timer.isActive():
            self._timer.start(0)

    @staticmethod
    def _registered(manager, namespace, entry, task):
        return (
            getattr(og, "task_manager", None) is manager
            and manager.imported_scripts.get(namespace) is entry
            and task in manager.task_map
            and any(current is task for current in entry.get("tasks", ()))
        )

    @Slot()
    def dispatch(self):
        if self._closed[0]:
            return
        if self._dispatching:
            self._schedule()
            return
        window = self._window()
        if window is None or not isValid(window):
            return
        manager = getattr(og, "task_manager", None)
        if manager is None:
            self._delivered.clear()
            return
        # Callbacks can remove or replace tasks. Snapshot both containers, then
        # recheck live registration immediately before each delivery.
        snapshot = tuple(
            (namespace, entry, task)
            for namespace, entry in tuple(manager.imported_scripts.items())
            for task in tuple(entry.get("tasks", ()))
        )
        live = {
            id(task): task
            for namespace, entry, task in snapshot
            if self._registered(manager, namespace, entry, task)
        }
        self._delivered = {
            identity: task
            for identity, task in self._delivered.items()
            if live.get(identity) is task
        }
        self._dispatching = True
        try:
            for namespace, entry, task in snapshot:
                if self._closed[0] or not isValid(window):
                    break
                if self._delivered.get(id(task)) is task:
                    continue
                if not self._registered(manager, namespace, entry, task):
                    continue
                try:
                    callback = getattr(task, "on_main_window", None)
                    if callable(callback):
                        # A failed partial initialization must not retry on
                        # unrelated task-list notifications.
                        self._delivered[id(task)] = task
                        callback(window)
                except Exception as error:
                    self._delivered[id(task)] = task
                    logger.error(
                        f"Plugin window hook failed: {namespace}/{type(task).__name__}",
                        error,
                    )
        finally:
            self._dispatching = False


def install_plugin_window_hooks(window):
    hooks = getattr(window, "_ok_plugin_window_hooks", None)
    if hooks is None:
        hooks = PluginWindowHooks(window)
        window._ok_plugin_window_hooks = hooks
    hooks.dispatch()
