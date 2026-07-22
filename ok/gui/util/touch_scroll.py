from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QAbstractButton, QScroller, QWidget


_FAKE_RELEASE_COORDINATE_LIMIT = -1_000_000


class _TouchScrollClickGuard(QObject):
    """Discard the synthetic mouse release belonging to a touch drag."""

    def __init__(self, scroll_area, scroller):
        super().__init__(scroll_area)
        self.scroll_area = scroll_area
        self.scroller = scroller
        self.dragged = False
        scroller.stateChanged.connect(self._on_state_changed)

    def _on_state_changed(self, state):
        if state in (QScroller.State.Dragging, QScroller.State.Scrolling):
            self.dragged = True

    def _is_content_widget(self, obj):
        content = self.scroll_area.widget()
        return (
            content is not None
            and isinstance(obj, QWidget)
            and (obj is content or content.isAncestorOf(obj))
        )

    @staticmethod
    def _is_scroller_fake_release(event):
        position = event.globalPosition()
        return (
            position.x() < _FAKE_RELEASE_COORDINATE_LIMIT
            and position.y() < _FAKE_RELEASE_COORDINATE_LIMIT
        )

    @staticmethod
    def _reset_pressed_state(widget):
        if isinstance(widget, QAbstractButton):
            widget.setDown(False)
        if hasattr(widget, "isPressed"):
            widget.isPressed = False
            widget.update()

    def eventFilter(self, obj, event):
        if not self._is_content_widget(obj):
            return False

        if event.type() == QEvent.MouseButtonPress:
            if self.scroller.state() in (
                QScroller.State.Dragging,
                QScroller.State.Scrolling,
            ):
                return True
            # This is a new click rather than the release from the old drag.
            self.dragged = False
        elif event.type() == QEvent.MouseButtonRelease and self.dragged:
            if self._is_scroller_fake_release(event):
                # QScroller normally sends this release far outside the
                # widget to cancel a click. Some custom widgets emit clicked
                # on every release, so consume it and reset them explicitly.
                self._reset_pressed_state(obj)
            else:
                self.dragged = False
            event.accept()
            return True

        return False


def enable_touch_scrolling(scroll_area):
    """Enable touch scrolling without activating children after a drag."""
    viewport = scroll_area.viewport()
    viewport.setAttribute(Qt.WA_AcceptTouchEvents, True)
    QScroller.grabGesture(
        viewport,
        QScroller.ScrollerGestureType.TouchGesture,
    )
    scroller = QScroller.scroller(viewport)
    guard = _TouchScrollClickGuard(scroll_area, scroller)
    QApplication.instance().installEventFilter(guard)
    scroll_area._touch_scroll_click_guard = guard
