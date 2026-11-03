from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QWidget

from ok.ui.qt.kit.feedback import ProgressRing
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.theme import theme


class StartLoadingDialog(QWidget):
    """A spinner over a dimmed window, optionally counting down a timeout."""

    def __init__(self, seconds_left: int, parent=None):
        window = parent.window() if parent is not None else None
        super().__init__(window)
        self.seconds_left = seconds_left
        self.panel = QFrame(self)
        self.panel.setObjectName("loadingPanel")
        self.spinner = ProgressRing(32, parent=self.panel)
        self.loading_label = Label("", "subtitle", self.panel)
        layout = QHBoxLayout(self.panel)
        layout.setContentsMargins(24, 18, 28, 18)
        layout.setSpacing(14)
        layout.addWidget(self.spinner)
        layout.addWidget(self.loading_label)
        self.timer = None
        self.set_seconds_left(seconds_left)
        self.restart_countdown(seconds_left)
        if window is not None:
            window.installEventFilter(self)
        theme.install(self)
        self.hide()

    def set_seconds_left(self, seconds_left: int):
        self.seconds_left = seconds_left
        if seconds_left > 0:
            text = self.tr('Starting, timeout after {seconds_left} seconds.').format(seconds_left=self.seconds_left)
        else:
            text = self.tr('Loading')
        self.loading_label.setText(text)
        self._fit()

    def restart_countdown(self, seconds_left: int):
        self.set_seconds_left(seconds_left)
        if seconds_left > 0:
            if self.timer is None:
                self.timer = QTimer(self)
                self.timer.setInterval(1000)
                self.timer.timeout.connect(self.update_countdown)
            self.timer.start()
        elif self.timer is not None:
            self.timer.stop()

    def update_countdown(self):
        self.seconds_left -= 1
        self.set_seconds_left(self.seconds_left)
        if self.seconds_left == 0:
            self.timer.stop()

    def show(self):
        self._fit()
        super().show()
        self.raise_()

    def close(self):
        if self.timer is not None:
            self.timer.stop()
        self.hide()
        return True

    def _fit(self):
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(parent.rect())
        self.panel.adjustSize()
        self.panel.move((self.width() - self.panel.width()) // 2, (self.height() - self.panel.height()) // 2)

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize and self.isVisible():
            self._fit()
        return False

    def mousePressEvent(self, event):
        # Block clicks to the page underneath while loading.
        event.accept()

    def paintEvent(self, _event):
        QPainter(self).fillRect(self.rect(), theme.color("scrim"))
