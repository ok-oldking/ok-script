# StartLoadingDialog.py
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import IndeterminateProgressRing, BodyLabel
from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase


class StartLoadingDialog(MaskDialogBase):
    """ Message box with animated countdown """

    def __init__(self, seconds_left: int, parent=None):
        super().__init__(parent=parent)
        self.seconds_left = seconds_left
        self.setModal(False)
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        self.spinner = IndeterminateProgressRing()
        self.spinner.setFixedSize(36, 36)
        self.spinner.setAlignment(Qt.AlignCenter)

        self.loading_label = BodyLabel()
        self.set_seconds_left(seconds_left)
        self.loading_label.setAlignment(Qt.AlignCenter)

        self.timer = None
        if seconds_left > 0:
            self.timer = QTimer(self)
            self.timer.setInterval(1000)
            self.timer.timeout.connect(self.update_countdown)
            self.timer.start()
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

    def set_seconds_left(self, seconds_left: int):
        self.seconds_left = seconds_left
        if seconds_left > 0:
            text = self.tr('Starting, timeout after {seconds_left} seconds.').format(seconds_left=self.seconds_left)
        else:
            text = self.tr('Loading')
        self.loading_label.setText(f'<h2>{text}</h2>')

    def update_countdown(self):
        self.seconds_left -= 1
        self.set_seconds_left(self.seconds_left)

        if self.seconds_left == 0:
            self.timer.stop()

    def close(self):
        super().close()
        if self.timer is not None:
            self.timer.stop()