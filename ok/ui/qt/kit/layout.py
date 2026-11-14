from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout


class FlowLayout(QLayout):
    """Wraps widgets left to right, with an optional cap on the preferred width."""

    def __init__(self, parent=None, spacing: int = 8, preferred_width: int = None):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self._preferred_width = preferred_width
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def spacing(self) -> int:
        return self._spacing

    def setSpacing(self, spacing: int) -> None:
        self._spacing = spacing
        self.invalidate()

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self) -> QSize:
        minimum = self.minimumSize()
        if self._preferred_width is None:
            return minimum

        widths = [item.sizeHint().width() for item in self._items if not item.isEmpty()]
        margins = self.contentsMargins()
        single_row_width = sum(widths) + max(0, len(widths) - 1) * self._spacing
        single_row_width += margins.left() + margins.right()
        width = max(minimum.width(), min(single_row_width, self._preferred_width))
        return QSize(width, self.heightForWidth(width))

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _arrange(self, rect: QRect, apply: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, line_height = area.x(), area.y(), 0
        for item in self._items:
            if item.widget() is not None and not item.widget().isVisible() and item.widget().parentWidget() \
                    and item.widget().parentWidget().isVisible():
                continue
            hint = item.sizeHint()
            if x + hint.width() > area.right() + 1 and line_height > 0:
                x = area.x()
                y += line_height + self._spacing
                line_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()
