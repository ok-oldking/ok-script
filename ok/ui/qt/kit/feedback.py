import shiboken6
from PySide6.QtCore import QEvent, QObject, QRectF, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.icons import icon as kit_icon
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.theme import set_style_property, theme

TONES = ("neutral", "accent", "success", "warning", "danger")
_TONE_COLOR = {"neutral": "text_tertiary", "accent": "accent", "success": "success", "warning": "warning",
               "danger": "danger"}
_TONE_ICON = {"neutral": "info", "accent": "info", "success": "check", "warning": "alert", "danger": "alert"}


def _check_tone(tone: str) -> str:
    if tone not in TONES:
        raise ValueError(f"unknown tone: {tone!r}")
    return tone


class Pill(QLabel):
    """A small rounded status label, e.g. "Running" or "Succeeded"."""

    def __init__(self, text: str = "", tone: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setProperty("tone", _check_tone(tone))
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def set_tone(self, tone: str) -> None:
        set_style_property(self, "tone", _check_tone(tone))


class StatusDot(QWidget):
    """A colored dot with a soft halo showing a connection or run state."""

    def __init__(self, tone: str = "neutral", parent=None):
        super().__init__(parent)
        self._tone = _check_tone(tone)
        self.setFixedSize(15, 15)
        theme.changed.connect(self.update)

    @property
    def tone(self) -> str:
        return self._tone

    def set_tone(self, tone: str) -> None:
        self._tone = _check_tone(tone)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = theme.color(_TONE_COLOR[self._tone])
        halo = QColor(color)
        halo.setAlphaF(0.2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(QRectF(0, 0, 15, 15))
        painter.setBrush(color)
        painter.drawEllipse(QRectF(3, 3, 9, 9))


class ProgressRing(QWidget):
    """A spinner; set ``value`` (0-100) for a determinate ring, ``None`` to spin."""

    def __init__(self, size: int = 20, value=None, parent=None):
        super().__init__(parent)
        self._value = value
        self._angle = 0
        self.setFixedSize(size, size)
        self._spin = QVariantAnimation(self)
        self._spin.setStartValue(0)
        self._spin.setEndValue(360)
        self._spin.setDuration(1000)
        self._spin.setLoopCount(-1)
        self._spin.valueChanged.connect(self._on_angle)
        theme.changed.connect(self.update)
        self._sync()

    def value(self):
        return self._value

    def set_value(self, value) -> None:
        self._value = None if value is None else max(0, min(100, value))
        self._sync()
        self.update()

    def is_spinning(self) -> bool:
        return self._spin.state() == QVariantAnimation.State.Running

    def _sync(self) -> None:
        if self._value is None and self.isVisible():
            self._spin.start()
        else:
            self._spin.stop()

    def _on_angle(self, angle) -> None:
        self._angle = angle
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._spin.stop()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = max(2.0, self.width() / 9)
        rect = QRectF(width / 2, width / 2, self.width() - width, self.height() - width)
        painter.setPen(QPen(theme.color("border_strong"), width))
        painter.drawEllipse(rect)
        pen = QPen(theme.accent(), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        if self._value is None:
            painter.drawArc(rect, int(-self._angle * 16), 100 * 16)
        else:
            painter.drawArc(rect, 90 * 16, int(-self._value * 3.6 * 16))


class Toast(QWidget):
    """A message card shown at the top center of a window; see :func:`show_toast`."""

    WIDTH = 560

    def __init__(self, message: str, title: str = None, tone: str = "neutral", action: tuple = None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.tone = _check_tone(tone)
        self.setFixedWidth(self.WIDTH)

        icon_label = QLabel(self)
        icon_label.setPixmap(kit_icon(_TONE_ICON[tone], _TONE_COLOR[tone], 2).pixmap(QSize(18, 18), self.devicePixelRatioF()))
        icon_label.setFixedSize(18, 18)
        self.title_label = Label(title or "", "strong", self, word_wrap=True)
        self.title_label.setVisible(bool(title))
        self.message_label = Label(message, "secondary" if title else "body", self, word_wrap=True)
        self.close_button = Button(icon="x", variant="subtle", size="small")
        self.close_button.setToolTip(self.tr("Close"))
        self.close_button.clicked.connect(self.close)

        text = QVBoxLayout()
        text.setSpacing(3)
        text.setContentsMargins(0, 0, 0, 0)
        text.addWidget(self.title_label)
        text.addWidget(self.message_label)
        self.action_button = None
        if action is not None:
            action_text, callback = action
            self.action_button = Button(action_text, size="small")
            self.action_button.clicked.connect(callback)
            text.addSpacing(6)
            text.addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignLeft)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 8, 12)
        layout.setSpacing(12)
        layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text, 1)
        layout.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)


class _ToastHost(QObject):
    """Stacks toasts down from a window's top center, below ``anchor`` if set."""

    SPACING = 8
    MARGIN = 16
    ANCHOR_GAP = 4

    def __init__(self, window: QWidget):
        super().__init__(window)
        self.window = window
        self.toasts = []
        self.anchor = None
        self.anchor_gap = self.ANCHOR_GAP
        self.top_margin = self.MARGIN
        window.installEventFilter(self)

    def add(self, toast: Toast, duration: int) -> None:
        toast.setParent(self.window)
        theme.install(toast)
        toast.destroyed.connect(lambda *_: self._forget(toast))
        toast.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.toasts.append(toast)
        self._fit(toast)
        toast.show()
        toast.raise_()
        self.layout()
        if duration > 0:
            QTimer.singleShot(duration, toast, toast.close)

    def _forget(self, toast) -> None:
        # Toasts are also destroyed while their window is being torn down.
        if not shiboken6.isValid(self.window):
            return
        if toast in self.toasts:
            self.toasts.remove(toast)
            self.layout()

    def _fit(self, toast) -> None:
        # Narrow windows shrink the toast; wrapped labels need height-for-width,
        # since adjustSize() would leave gaps.
        width = max(240, min(Toast.WIDTH, self.window.width() - 2 * self.MARGIN))
        toast.setFixedWidth(width)
        toast.resize(width, toast.layout().totalHeightForWidth(width))

    def _top(self) -> int:
        anchor = self.anchor
        if anchor is not None and shiboken6.isValid(anchor) and anchor.isVisible():
            return anchor.mapTo(self.window, anchor.rect().bottomLeft()).y() + 1 + self.anchor_gap
        return self.top_margin

    def layout(self) -> None:
        self.toasts = [toast for toast in self.toasts if toast.isVisible()]
        y = self._top()
        for toast in self.toasts:
            toast.move((self.window.width() - toast.width()) // 2, y)
            y += toast.height() + self.SPACING

    def eventFilter(self, watched, event) -> bool:
        if watched is self.window and event.type() == QEvent.Type.Resize:
            for toast in self.toasts:
                self._fit(toast)
            self.layout()
        return False


def toast_host(widget: QWidget) -> _ToastHost:
    window = widget.window()
    host = window.findChild(_ToastHost, options=Qt.FindChildOption.FindDirectChildrenOnly)
    return host or _ToastHost(window)


def show_toast(parent: QWidget, message: str, title: str = None, tone: str = "neutral",
               duration: int = 4000, action: tuple = None) -> Toast:
    """Show a toast in ``parent``'s window.

    ``duration`` 0 keeps it until closed; ``action`` is ``(text, callback)``
    for a button inside the toast.
    """

    toast = Toast(message, title, tone, action)
    toast_host(parent).add(toast, duration)
    return toast


def set_toast_anchor(widget: QWidget, anchor: QWidget, *, gap: int = 4) -> None:
    """Show toasts below ``anchor`` with the requested gap in logical pixels."""

    host = toast_host(widget)
    host.anchor = anchor
    host.anchor_gap = max(0, int(gap))
    host.layout()


def set_toast_top_margin(widget: QWidget, margin: int) -> None:
    """Position toasts directly below the window's top edge."""

    host = toast_host(widget)
    host.anchor = None
    host.top_margin = max(0, int(margin))
    host.layout()
