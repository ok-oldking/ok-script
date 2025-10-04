from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget, QSizePolicy
from qfluentwidgets import ScrollArea

from ok.gui.common.style_sheet import StyleSheet
from ok.gui.widget.Card import Card
from ok.gui.widget.StartLoadingDialog import StartLoadingDialog


class Tab(ScrollArea):
    def __init__(self):
        super().__init__()
        self.loading_dialog = None
        self.view = QWidget(self)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.vBoxLayout = QVBoxLayout(self.view)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportMargins(0, 0, 0, 0)
        self.setWidget(self.view)
        self.setWidgetResizable(True)

        self.vBoxLayout.setSpacing(4)
        self.vBoxLayout.setAlignment(Qt.AlignTop)
        self.vBoxLayout.setContentsMargins(16, 16, 16, 16)

        self.view.setObjectName('view')

        self.setObjectName(self.__class__.__name__)
        StyleSheet.TAB.apply(self)

    @property
    def exit_event(self):
        from ok import og
        return og.ok.exit_event

    def show_loading_dialog(self):
        if not self.loading_dialog:
            self.loading_dialog = StartLoadingDialog(-1,
                                                     self.window())
        if not self.loading_dialog.isVisible():
            self.loading_dialog.show()

    def hide_loading_dialog(self):
        if self.loading_dialog is not None:
            self.loading_dialog.close()

    def add_card(self, title, widget, stretch=0, parent=None):
        container = Card(title, widget, stretch=stretch)
        self.add_widget(container, stretch)
        return container

    def add_widget(self, *args, **kwargs):
        self.vBoxLayout.addWidget(*args, **kwargs)

    def removeWidget(self, widget):
        self.vBoxLayout.removeWidget(widget)

    def addLayout(self, layout, stretch=0):
        self.vBoxLayout.addLayout(layout, stretch)
        return layout
