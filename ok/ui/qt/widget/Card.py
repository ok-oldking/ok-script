from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLayout, QSizePolicy, QVBoxLayout, QWidget

from ok.ui.qt.kit.cards import Card as KitCard
from ok.ui.qt.kit.labels import Label


class Card(QWidget):
    """A titled section: an optional heading above a kit card that holds ``widget``."""

    def __init__(self, title, widget, stretch=0, parent=None):
        super().__init__(parent=parent)
        if isinstance(widget, QLayout):
            self.widget = QWidget()
            self.widget.setLayout(widget)
        else:
            self.widget = widget
        self.stretch = stretch

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(10)
        self.title_layout = None
        self.titleLabel = None
        if title:
            self.title_layout = QHBoxLayout()
            self.titleLabel = Label(title, "subtitle", self)
            self.title_layout.addWidget(self.titleLabel)
            self.title_layout.addStretch(1)
            self.vBoxLayout.addLayout(self.title_layout)

        self.card = KitCard(self)
        self.cardLayout = QVBoxLayout(self.card)
        self.cardLayout.setContentsMargins(20, 16, 20, 16)
        self.cardLayout.setSpacing(12)
        self.topLayout = QHBoxLayout()
        self.topLayout.setContentsMargins(0, 0, 0, 0)
        self.cardLayout.addLayout(self.topLayout, stretch)
        self.widget.setParent(self.card)
        self.topLayout.addWidget(self.widget, stretch)
        self.vBoxLayout.addWidget(self.card, stretch)
        if stretch == 1:
            self.card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        else:
            self.vBoxLayout.setAlignment(Qt.AlignTop)
            self.cardLayout.setAlignment(Qt.AlignTop)

    def add_top_widget(self, widget):
        self.title_layout.addWidget(widget)
