from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QScroller


def enable_touch_scrolling(scroll_area):
    """Enable touch scrolling without activating children after a drag."""
    viewport = scroll_area.viewport()
    QScroller.grabGesture(
        viewport,
        QScroller.ScrollerGestureType.TouchGesture,
    )
    scroller = QScroller.scroller(viewport)

    def set_content_mouse_transparent(transparent):
        content = scroll_area.widget()
        if content is not None:
            content.setAttribute(Qt.WA_TransparentForMouseEvents, transparent)

    def on_state_changed(state):
        if state in (QScroller.State.Dragging, QScroller.State.Scrolling):
            set_content_mouse_transparent(True)
        elif state == QScroller.State.Inactive:
            # Restore clicks only after the release event that ended the
            # gesture has finished propagating.
            QTimer.singleShot(0, lambda: set_content_mouse_transparent(False))

    scroller.stateChanged.connect(on_state_changed)
    # Keep the Python callback alive for as long as the scroll area exists.
    scroll_area._touch_scroll_state_handler = on_state_changed

