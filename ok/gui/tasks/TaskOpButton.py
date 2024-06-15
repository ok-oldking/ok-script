from PySide6.QtCore import Slot
from PySide6.QtWidgets import QPushButton

from ok.logging.Logger import get_logger
from ok.task.BaseTask import BaseTask

logger = get_logger(__name__)


class TaskOpButton(QPushButton):
    def __init__(self, task: BaseTask):
        super().__init__("Enable")
        self.clicked.connect(self.toggle_text)
        self.task = task

    def update_task(self, task: BaseTask):
        if task.enabled:
            self.setText(self.tr("Disable"))
        else:
            self.setText(self.tr("Enable"))

    @Slot()
    def toggle_text(self):
        if self.task.enabled:
            self.task.disable()
        else:
            self.task.disable()
