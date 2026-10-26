from concurrent.futures import Future, TimeoutError

from PySide6.QtCore import QCoreApplication, QObject, QThread, Signal, Slot

from ok.core.task_manager import TaskManager as CoreTaskManager


class ReloadDispatcher(QObject):
    requested = Signal(object, object)

    def __init__(self):
        super().__init__()
        self.requested.connect(self._run)

    @Slot(object, object)
    def _run(self, fn, future):
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(fn())
        except BaseException as error:
            future.set_exception(error)

    def call(self, fn, exit_event):
        app = QCoreApplication.instance()
        if app is None or QThread.currentThread() is app.thread():
            return fn()
        future = Future()
        self.requested.emit(fn, future)
        while True:
            try:
                return future.result(timeout=0.1)
            except TimeoutError:
                if future.done():
                    raise
                if exit_event.is_set() and future.cancel():
                    raise RuntimeError('Application closed before tasks could reload')


class TaskManager(CoreTaskManager):
    def __init__(self, *args, **kwargs):
        self._reload_dispatcher = ReloadDispatcher()
        kwargs.setdefault('defer_plugin_validation', True)
        super().__init__(*args, **kwargs)

    def _dispatch_reload(self, tasks):
        return self._reload_dispatcher.call(
            lambda: self._reload_tasks(tasks), self.task_executor.exit_event)


__all__ = ["TaskManager"]
