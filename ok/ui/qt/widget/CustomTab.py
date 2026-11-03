from ok import Logger
from ok import TaskExecutor
from ok.core.icons import Icon
from ok.ui.qt.widget.Tab import Tab


class CustomTab(Tab):
    """Base class for pages an app or plugin adds to the Game section.

    Set :attr:`icon` to an :class:`ok.core.icons.Icon` or an SVG/PNG path, and
    override :attr:`name`. Build the page with :meth:`add_card` and
    :meth:`add_widget`.
    """

    icon = Icon.APPLICATION

    def __init__(self):
        super().__init__()
        self.logger = Logger.get_logger(self.__class__.__name__)
        self.executor: TaskExecutor | None = None

    def get_task(self, cls):
        return self.executor.get_task_by_class(cls)

    def tr(self, message):
        from ok import og
        if og.app:
            return og.app.tr(message)
        return super().tr(message)

    @property
    def name(self):
        return "CustomTab"

    @property
    def add_after_default_tabs(self):
        return True
