from PySide6.QtWidgets import QWidgetItem
from qfluentwidgets import ExpandLayout


class ExpandCardLayout(ExpandLayout):
    """Project adapter around the official ``qfluentwidgets.ExpandLayout``.

    The official layout is retained for its expand-animation behaviour.  The
    adapter gives direct children the correct parent while retaining the
    standard ``QLayout`` item lifecycle used by dynamically refreshed lists.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

    def addWidget(self, widget, stretch=0, alignment=None):
        if self.indexOf(widget) >= 0:
            return

        parent = self.parentWidget()
        if parent is not None and widget.parentWidget() is not parent:
            widget.setParent(parent)

        super().addWidget(widget)
        self.addItem(QWidgetItem(widget))
