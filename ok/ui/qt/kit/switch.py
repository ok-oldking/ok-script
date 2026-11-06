from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QSizePolicy

from ok.ui.qt.kit.theme import theme


class Switch(QAbstractButton):
    """An on/off toggle drawn to match the kit; ``toggled`` reports changes."""

    WIDTH = 42
    HEIGHT = 24

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._position = 1.0 if checked else 0.0
        self._animation = QPropertyAnimation(self, b"position", self)
        self._animation.setDuration(140)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setChecked(checked)
        self.toggled.connect(self._animate)
        theme.changed.connect(self.update)

    def sizeHint(self) -> QSize:
        return QSize(self.WIDTH, self.HEIGHT)

    def _get_position(self) -> float:
        return self._position

    def _set_position(self, value: float) -> None:
        self._position = value
        self.update()

    position = Property(float, _get_position, _set_position)

    def _animate(self, checked: bool) -> None:
        self._animation.stop()
        if not self.isVisible():
            self._set_position(1.0 if checked else 0.0)
            return
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(0.5, 0.5, self.WIDTH - 1, self.HEIGHT - 1)
        radius = track.height() / 2
        enabled = self.isEnabled()
        # setChecked() with signals blocked skips the animation; draw the real state then.
        if self._animation.state() != QPropertyAnimation.State.Running:
            self._position = 1.0 if self.isChecked() else 0.0
        p = self._position

        if self.isChecked():
            color = theme.accent()
            if not enabled:
                color.setAlphaF(0.4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
        else:
            painter.setPen(QPen(theme.color("switch_off" if enabled else "border"), 1))
            painter.setBrush(theme.color("control"))
        painter.drawRoundedRect(track, radius, radius)

        knob = 14 + 4 * p
        x = 4 + (self.WIDTH - 8 - knob) * p
        y = (self.HEIGHT - knob) / 2
        if self.isChecked():
            knob_color = theme.color("on_accent")
            if not enabled:
                knob_color.setAlphaF(0.7)
        else:
            knob_color = theme.color("text_secondary" if enabled else "text_disabled")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_color)
        painter.drawEllipse(QRectF(x, y, knob, knob))

        if self.hasFocus() and self.focusPolicy() != Qt.FocusPolicy.NoFocus and self._keyboard_focus:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(theme.accent(), 1.5))
            painter.drawRoundedRect(track.adjusted(-0.5, -0.5, 0.5, 0.5), radius, radius)

    _keyboard_focus = False

    def focusInEvent(self, event) -> None:
        self._keyboard_focus = event.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason)
        super().focusInEvent(event)

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)
