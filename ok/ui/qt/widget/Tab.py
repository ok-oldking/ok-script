from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from ok.ui.qt.kit.theme import theme
from ok.ui.qt.util.touch_scroll import enable_touch_scrolling
from ok.ui.qt.widget.Card import Card
from ok.ui.qt.widget.StartLoadingDialog import StartLoadingDialog

PAGE_MARGINS = (28, 20, 28, 28)
PAGE_SPACING = 24


class Tab(QScrollArea):
    """A scrolling page for app and plugin tabs: add titled cards or widgets to :attr:`vBoxLayout`."""

    def __init__(self):
        super().__init__()
        self.loading_dialog = None
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.view = QWidget(self)
        self.view.setObjectName('scrollContents')
        self.vBoxLayout = QVBoxLayout(self.view)
        self.vBoxLayout.setContentsMargins(*PAGE_MARGINS)
        self.vBoxLayout.setSpacing(PAGE_SPACING)
        self.vBoxLayout.setAlignment(Qt.AlignTop)
        self.setWidget(self.view)
        enable_touch_scrolling(self)
        self.setObjectName(f"{self.__class__.__name__}_{id(self)}")
        theme.install(self)

    @property
    def exit_event(self):
        from ok import og
        return og.ok.exit_event

    def get_overlay_view(self):
        from ok import og
        return og.get_overlay_view()

    def show_loading_dialog(self):
        if not self.loading_dialog:
            self.loading_dialog = StartLoadingDialog(-1, self)
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
