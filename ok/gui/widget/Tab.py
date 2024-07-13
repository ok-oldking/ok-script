from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget, QSizePolicy
from qfluentwidgets import ScrollArea

from ok.gui.common.style_sheet import StyleSheet
from ok.gui.widget.Card import Card


class Tab(ScrollArea):
    def __init__(self):
        super().__init__()
        self.view = QWidget(self)
        self.vBoxLayout = QVBoxLayout(self.view)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportMargins(0, 0, 0, 0)
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.vBoxLayout.setSpacing(30)
        self.vBoxLayout.setAlignment(Qt.AlignTop)
        self.vBoxLayout.setContentsMargins(36, 20, 36, 36)

        self.view.setObjectName('view')

        self.setObjectName(self.__class__.__name__)
        StyleSheet.TAB.apply(self)

    def addCard(self, title, widget, stretch=0, parent=None):
        container = Card(title, widget)
        self.addWidget(container, stretch)
        return container

    def addWidget(self, widget, stretch=0, align=Qt.AlignTop):
        self.vBoxLayout.addWidget(widget, stretch, align)
        return widget

    def addLayout(self, layout, stretch=0):
        self.vBoxLayout.addLayout(layout, stretch)
        return layout
