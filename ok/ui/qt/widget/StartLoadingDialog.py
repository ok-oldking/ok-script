# StartLoadingDialog.py
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import IndeterminateProgressRing, BodyLabel, PushButton
from ok import og
from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase


class StartLoadingDialog(MaskDialogBase):
    """ Message box with animated countdown """

    def __init__(self, seconds_left: int, parent=None):
        super().__init__(parent=parent)
        self.seconds_left = seconds_left
        device = og.device_manager.get_preferred_device()
        self.macos_foreground = bool(device and device.get('device') == 'macos')
        self.setModal(False)
        if self.macos_foreground:
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        self.spinner = IndeterminateProgressRing()
        self.spinner.setFixedSize(36, 36)
        self.spinner.setAlignment(Qt.AlignCenter)

        self.loading_label = BodyLabel()
        self.set_seconds_left(seconds_left)
        self.loading_label.setAlignment(Qt.AlignCenter)

        self.timer = None
        self.restart_countdown(seconds_left)
        self.widget.setLayout(layout)

        layout.addStretch(1)
        layout.addWidget(self.spinner)
        layout.addSpacing(10)
        layout.addWidget(self.loading_label)
        if self.macos_foreground:
            self.cancel_button = PushButton('取消启动', self)
            self.cancel_button.clicked.connect(og.app.start_controller.cancel_start)
            layout.addWidget(self.cancel_button)
        layout.addStretch(1)

        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 50))
        self.setMaskColor(QColor(0, 0, 0, 76))
        self._hBoxLayout.removeWidget(self.widget)
        self._hBoxLayout.addWidget(self.widget, 1, Qt.AlignCenter)

    def set_seconds_left(self, seconds_left: int):
        self.seconds_left = seconds_left
        if seconds_left > 0:
            text = (f'请切回游戏，等待前台就绪（{seconds_left}秒） / Switch to game'
                    if self.macos_foreground else
                    self.tr('Starting, timeout after {seconds_left} seconds.').format(seconds_left=self.seconds_left))
        else:
            text = self.tr('Loading')
        self.loading_label.setText(f'<h2>{text}</h2>')

    def restart_countdown(self, seconds_left: int):
        self.set_seconds_left(seconds_left)
        if self.macos_foreground:
            return  # Controller's monotonic deadline is the only clock on Mac.
        if seconds_left > 0:
            if self.timer is None:
                self.timer = QTimer(self)
                self.timer.setInterval(1000)
                self.timer.timeout.connect(self.update_countdown)
            self.timer.start()
        elif self.timer is not None:
            self.timer.stop()

    def set_macos_status(self, phase, seconds_left):
        self.seconds_left = seconds_left
        label = '请切回游戏，等待切换' if phase == 'foreground' else '任务准备中'
        self.loading_label.setText(f'<h2>{label}：剩余 {seconds_left} 秒</h2>')

    def update_countdown(self):
        self.seconds_left -= 1
        self.set_seconds_left(self.seconds_left)

        if self.seconds_left == 0:
            self.timer.stop()

    def close(self):
        super().close()
        if self.timer is not None:
            self.timer.stop()
