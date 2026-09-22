from PySide6.QtCore import Slot, QPropertyAnimation
from PySide6.QtGui import QColor
from qfluentwidgets import PushButton

from ok import Logger, og
from ok.ui.qt.Communicate import communicate

logger = Logger.get_logger(__name__)


class StartButton(PushButton):
    def __init__(self):
        super().__init__("Start")
        self.setCheckable(True)
        self.clicked.connect(self.toggle_text)
        self.animation = QPropertyAnimation(self, b"color")
        self.update_paused(True)
        communicate.executor_paused.connect(self.update_paused)
        communicate.starting_emulator.connect(self.on_starting_result)

    def on_starting_result(self, done, error, seconds_left):
        # A failed start leaves the executor paused; resync the check state.
        if error and og.executor.paused:
            self.update_paused(True)

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
            # Share the unified start flow: direct start when the game is
            # already connected, launch+connect otherwise.
            og.app.start_controller.start()
        else:
            logger.info("Click Pause Executor")
            og.executor.pause()

    def start_animation(self):
        self.animation.setStartValue(QColor(0, 0, 0))
        self.animation.setEndValue(QColor(255, 255, 255))
        self.animation.setDuration(1000)
        self.animation.start()
