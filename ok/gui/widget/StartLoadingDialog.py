from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QLabel, QHBoxLayout
from qfluentwidgets import IndeterminateProgressRing
from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase


class StartLoadingDialog(MaskDialogBase):
    """ Message box with animated countdown """

    def __init__(self, seconds_left: int, parent=None):
        super().__init__(parent=parent)
        self.seconds_left = seconds_left
        self.vBoxLayout = QVBoxLayout(parent)
        self.setModal(False)
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        # Create a QProgressBar for the spinner
        self.spinner = IndeterminateProgressRing()
        self.spinner.setFixedSize(36, 36)
        self.spinner.setAlignment(Qt.AlignCenter)

        # Create a QLabel for the loading text
        self.loading_label = QLabel()
        self.set_seconds_left(seconds_left)
        self.loading_label.setAlignment(Qt.AlignCenter)

        # Create a timer to update the countdown
        self.timer = QTimer(self)
        self.timer.setInterval(1000)  # Update every second
        self.timer.timeout.connect(self.update_countdown)

        # self.widget = QWidget()
        self.widget.setLayout(layout)

        layout.addStretch(1)
        layout.addWidget(self.spinner)
        layout.addSpacing(10)
        layout.addWidget(self.loading_label)
        layout.addStretch(1)

        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 50))
        self.setMaskColor(QColor(0, 0, 0, 76))
        self._hBoxLayout.removeWidget(self.widget)
        self._hBoxLayout.addWidget(self.widget, 1, Qt.AlignCenter)

        # Start the timer
        self.timer.start()

    def set_seconds_left(self, seconds_left: int):
        self.seconds_left = seconds_left
        text = self.tr('Starting, timeout after {seconds_left} seconds.').format(seconds_left=self.seconds_left)
        self.loading_label.setText(f'<h2>{text}</h2>')

    def update_countdown(self):
        self.seconds_left -= 1
        self.set_seconds_left(self.seconds_left)

        # Stop timer and close dialog when countdown reaches zero
        if self.seconds_left == 0:
            self.timer.stop()

    def close(self):
        super().close()
        self.timer.stop()
