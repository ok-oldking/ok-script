from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout


class FlowLayout(QWidget):
    """A simple flow layout widget that wraps child widgets into rows and
    reflows when the container is resized.

    Usage:
        flow = FlowLayout()
        flow.add_widget(btn)
        parent_layout.addWidget(flow)
    """

    def __init__(self):
        super().__init__()
        self.vbox = QVBoxLayout()
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.setSpacing(5)
        self.setLayout(self.vbox)

        self._widgets = []

    def add_widget(self, widget):
        """Register a child widget and trigger a reflow."""
        # Ensure the widget has this widget as parent to get proper size hints
        if widget.parent() is None:
            widget.setParent(self)
        self._widgets.append(widget)
        self.reflow()

    def clear_layouts(self):
        # Remove all hboxes from vbox (but don't delete child widgets)
        while self.vbox.count():
            item = self.vbox.takeAt(0)
            # item may be a layout; remove its items
            if item.layout():
                l = item.layout()
                while l.count():
                    child = l.takeAt(0)
                    # nothing to delete here; widgets remain

    def reflow(self):
        """Arrange widgets into rows based on current width."""
        # clear existing rows
        self.clear_layouts()

        if not self._widgets:
            return

        current_hbox = QHBoxLayout()
        current_hbox.setAlignment(Qt.AlignLeft)
        current_width = 0
        spacing = self.vbox.spacing()
        self.vbox.addLayout(current_hbox)

        available_width = max(1, self.width())

        for w in self._widgets:
            w_hint = w.sizeHint()
            widget_w = w_hint.width()

            # If adding this widget would exceed available width, start new row
            if current_width and (current_width + widget_w + spacing) > available_width:
                current_hbox = QHBoxLayout()
                current_hbox.setAlignment(Qt.AlignLeft)
                self.vbox.addLayout(current_hbox)
                current_width = 0

            current_hbox.addWidget(w)
            current_width += widget_w + spacing

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()
