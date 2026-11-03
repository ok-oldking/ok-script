"""Input and wait helpers for Qt tests.

ok-pyside-minimal has no QtTest, so tests send events directly. Events go
through ``QApplication.sendEvent``, which also runs application-wide event
filters.
"""

import time

from PySide6.QtCore import QEvent, QEventLoop, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication


def wait(ms: int) -> None:
    """Process events for ``ms`` milliseconds, like ``QTest.qWait``."""
    deadline = time.monotonic() + ms / 1000
    while time.monotonic() < deadline:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
        time.sleep(0.002)
    QApplication.processEvents()


def mouse_click(widget, button=Qt.MouseButton.LeftButton, pos: QPoint = None) -> None:
    """Press and release ``button`` at ``pos`` (default: the widget's center)."""
    local = QPointF(pos if pos is not None else widget.rect().center())
    global_pos = QPointF(widget.mapToGlobal(local.toPoint()))
    for event_type, buttons in ((QEvent.Type.MouseButtonPress, button),
                                (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
        event = QMouseEvent(event_type, local, global_pos, button, buttons, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(widget, event)
    QApplication.processEvents()


def key_click(widget, key, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
    """Press and release ``key`` on ``widget``."""
    for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(widget, QKeyEvent(event_type, key, modifiers))
    QApplication.processEvents()
