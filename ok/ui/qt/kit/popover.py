from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtWidgets import QApplication, QFrame, QWidget

from ok.ui.qt.kit.theme import theme


class Popover(QFrame):
    """A floating card inside its window, anchored to a widget.

    It closes on Esc and on a click outside it (other than on the anchor, which
    usually toggles it). It stays open while the window is inactive, so it
    also works when the window was opened in the background.
    """

    closed = Signal()

    def __init__(self, parent: QWidget):
        window = parent.window()
        super().__init__(window)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._anchor = None
        self._above = True
        self._gap = 8
        theme.install(self)
        self.hide()

    def popup(self, anchor: QWidget, above: bool = True, gap: int = 8) -> None:
        """Show next to ``anchor``, left-aligned with it and kept inside the window."""

        self._anchor = anchor
        self._above = above
        self._gap = gap
        # The popover may have been built before its owner joined a window.
        window = anchor.window()
        if self.parentWidget() is not window:
            self.setParent(window)
        self.reposition()
        self.show()
        self.raise_()
        self.setFocus()
        QApplication.instance().installEventFilter(self)

    def reposition(self) -> None:
        """Re-measure and re-place the popover, e.g. after its content changed."""

        if self._anchor is None:
            return
        window = self.parentWidget()
        layout = self.layout()
        if layout is not None:
            # Word-wrapped labels only report their real height for a given width.
            layout.activate()
            height = layout.totalHeightForWidth(self.width()) if layout.hasHeightForWidth() \
                else layout.totalSizeHint().height()
            self.resize(self.width(), min(height, window.height() - 16))
        else:
            self.adjustSize()
        top_left = self._anchor.mapTo(window, QPoint(0, 0))
        x = max(8, min(top_left.x(), window.width() - self.width() - 8))
        if self._above:
            y = top_left.y() - self.height() - self._gap
        else:
            y = top_left.y() + self._anchor.height() + self._gap
        self.move(x, max(8, min(y, window.height() - self.height() - 8)))

    def toggle(self, anchor: QWidget, above: bool = True) -> None:
        if self.isVisible():
            self.close_popover()
        else:
            self.popup(anchor, above)

    def close_popover(self) -> None:
        if not self.isVisible():
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.hide()
        self.closed.emit()

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(watched, QWidget) and watched.isWindow() \
                is False and self.isVisible():
            if not self._contains(watched) and not self._is_anchor(watched) and not self._is_own_popup(watched):
                self.close_popover()
        return False

    def _contains(self, widget: QWidget) -> bool:
        return widget is self or self.isAncestorOf(widget)

    def _is_anchor(self, widget: QWidget) -> bool:
        anchor = self._anchor
        return anchor is not None and (widget is anchor or anchor.isAncestorOf(widget))

    def _is_own_popup(self, widget: QWidget) -> bool:
        # Combo box popups are separate windows whose parent chain leads back here.
        window = widget.window()
        parent = window.parentWidget() if window is not None else None
        return parent is not None and self._contains(parent)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_popover()
        else:
            super().keyPressEvent(event)
