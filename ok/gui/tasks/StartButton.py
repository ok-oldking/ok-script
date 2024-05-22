from PySide6.QtCore import Slot, QPropertyAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QPushButton
from qfluentwidgets import PushButton

import ok
from ok.gui.Communicate import communicate
from ok.gui.util.Alert import show_alert
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class StartButton(PushButton):
    def __init__(self):
        super().__init__("Start")
        self.setCheckable(True)
        self.clicked.connect(self.toggle_text)
        self.animation = QPropertyAnimation(self, b"color")
        self.update_paused(True)
        communicate.executor_paused.connect(self.update_paused)

    def update_paused(self, paused):
        if paused:
            self.setText(self.tr("Start All"))
            self.setChecked(False)
            self.animation.stop()
        else:
            self.setText(self.tr("Pause All"))
            self.setChecked(True)
            self.start_animation()

    @Slot()
    def toggle_text(self):
        if self.isChecked():
            logger.info("Click Start Executor")
            if not ok.gui.executor.start():
                show_alert("Error", "No Task to Run, Please Enable Task First!")
                self.setChecked(False)
        else:
            logger.info("Click Pause Executor")
            ok.gui.executor.pause()

    def start_animation(self):
        self.animation.setStartValue(QColor(0, 0, 0))
        self.animation.setEndValue(QColor(255, 255, 255))
        self.animation.setDuration(1000)
        self.animation.start()
