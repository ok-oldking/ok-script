from qfluentwidgets import NavigationItemPosition

from ok import Logger
from ok import TaskExecutor
from ok.gui.widget.Tab import Tab


class CustomTab(Tab):
    def __init__(self):
        super().__init__()
        self.logger = Logger.get_logger(self.__class__.__name__)
        self.executor: TaskExecutor | None = None

    def get_task(self, cls):
        return self.executor.get_task_by_class(cls)

    @property
    def name(self):
        return "CustomTab"

    @property
    def position(self):
        return NavigationItemPosition.TOP

    @property
    def add_after_default_tabs(self):
        return True
