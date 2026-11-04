"""Selection and page transitions shared by the kit's navigation widgets.

Both follow the Fluent motion guidance: a short decelerating ease, the
selection indicator travels from the old item to the new one, and the
incoming page enters with a small slide plus fade.
"""

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QRect, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget, QWidget

INDICATOR_DURATION = 250
PAGE_DURATION = 250
PAGE_DISTANCE = 24


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_rect(a: QRectF, b: QRectF, t: float) -> QRectF:
    return QRectF(_lerp(a.x(), b.x(), t), _lerp(a.y(), b.y(), t),
                  _lerp(a.width(), b.width(), t), _lerp(a.height(), b.height(), t))


class SlidingIndicator:
    """Tracks the selected item of ``host`` and glides between items.

    ``rect_for(item)`` returns the indicator's rect in ``host`` coordinates.
    It is called on every paint, so the indicator follows the item while it
    moves or resizes (scrolling, a collapsing sidebar). The host draws the
    rect returned by :meth:`rect` in its ``paintEvent``.
    """

    def __init__(self, host: QWidget, rect_for, duration: int = INDICATOR_DURATION):
        self._host = host
        self._rect_for = rect_for
        self._item = None
        self._start = None
        self._progress = 1.0
        self._animation = QVariantAnimation(host)
        self._animation.setDuration(duration)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.valueChanged.connect(self._on_progress)

    def item(self):
        return self._item

    def set_item(self, item, animate: bool = True) -> None:
        """Move the indicator to ``item``; ``None`` hides it."""

        if item is self._item:
            return
        start = self.rect()
        self._animation.stop()
        self._item = item
        if animate and item is not None and start is not None and self._host.isVisible():
            self._start = start
            self._progress = 0.0
            self._animation.start()
        else:
            self._start = None
            self._progress = 1.0
        self._host.update()

    def rect(self):
        """The indicator's current rect in host coordinates, or ``None``."""

        item = self._item
        if item is None:
            return None
        try:
            if not item.isVisibleTo(self._host):
                return None
            target = self._rect_for(item)
        except RuntimeError:  # the item was deleted
            self._item = None
            return None
        if target is None:
            return None
        target = QRectF(target)
        if self._start is None or self._progress >= 1.0:
            return target
        return _lerp_rect(self._start, target, self._progress)

    def is_animating(self) -> bool:
        return self._animation.state() == QAbstractAnimation.State.Running

    def _on_progress(self, value) -> None:
        self._progress = float(value)
        if self._progress >= 1.0:
            self._start = None
        self._host.update()


def paint_rounded(widget: QWidget, rect: QRectF, radius: float, fill, border=None) -> None:
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if border is not None:
        painter.setPen(border)
        rect = rect.adjusted(0.5, 0.5, -0.5, -0.5)
    else:
        painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(fill)
    painter.drawRoundedRect(rect, radius, radius)
    painter.end()


class AnimatedStackedWidget(QStackedWidget):
    """A stacked widget whose incoming page slides in and fades in.

    ``orientation`` is ``Qt.Orientation.Vertical`` for page navigation
    (the page rises into place) or ``Qt.Orientation.Horizontal`` for tabs
    (the page enters from the side of the newly selected tab).
    """

    def __init__(self, orientation=Qt.Orientation.Vertical, distance: int = PAGE_DISTANCE,
                 duration: int = PAGE_DURATION, parent=None):
        super().__init__(parent)
        self._orientation = orientation
        self._distance = distance
        self._page = None
        self._sign = 1
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(duration)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.valueChanged.connect(self._step)
        self._animation.finished.connect(self._settle)

    def setCurrentWidget(self, widget) -> None:
        index = self.indexOf(widget)
        if index >= 0:
            self.setCurrentIndex(index)

    def setCurrentIndex(self, index: int) -> None:
        previous = self.currentIndex()
        if index == previous or not 0 <= index < self.count():
            super().setCurrentIndex(index)
            return
        self._settle()
        super().setCurrentIndex(index)
        if previous >= 0:
            horizontal = self._orientation == Qt.Orientation.Horizontal
            self._enter(-1 if horizontal and index < previous else 1)

    def animate_current(self) -> None:
        """Play the entrance of the current page again, e.g. once it has finished loading."""

        self._settle()
        self._enter(self._sign)

    def _enter(self, sign: int) -> None:
        page = self.currentWidget()
        if page is None or not self.isVisible() or self._animation.duration() <= 0:
            return
        if page.graphicsEffect() is not None:
            return  # never replace an effect the page owns
        self._sign = sign
        page.setGraphicsEffect(QGraphicsOpacityEffect(page))
        self._page = page
        self._step(0.0)
        self._animation.start()

    def is_animating(self) -> bool:
        return self._page is not None

    def _step(self, value) -> None:
        page = self._page
        if page is None:
            return
        progress = float(value)
        offset = round((1.0 - progress) * self._distance) * self._sign
        rect = self.contentsRect()
        if self._orientation == Qt.Orientation.Horizontal:
            rect.translate(offset, 0)
        else:
            rect.translate(0, offset)
        try:
            page.setGeometry(rect)
            effect = page.graphicsEffect()
            if isinstance(effect, QGraphicsOpacityEffect):
                effect.setOpacity(progress)
        except RuntimeError:  # the page was deleted mid-transition
            self._page = None
            self._animation.stop()

    def _settle(self) -> None:
        page, self._page = self._page, None
        self._animation.stop()
        if page is None:
            return
        try:
            page.setGeometry(QRect(self.contentsRect()))
            if isinstance(page.graphicsEffect(), QGraphicsOpacityEffect):
                page.setGraphicsEffect(None)
        except RuntimeError:
            pass
