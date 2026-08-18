from PySide6.QtCore import QFileSystemWatcher

from ok.core.task_manager import TaskManager as CoreTaskManager


class TaskManager(CoreTaskManager):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("file_watcher_factory", QFileSystemWatcher)
        super().__init__(*args, **kwargs)


__all__ = ["TaskManager"]
