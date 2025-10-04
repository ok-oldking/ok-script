from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QSizePolicy, QWidget, QHBoxLayout, QSpacerItem, QFrame, QLayout
from qfluentwidgets import StrongBodyLabel

from ok.gui.common.style_sheet import StyleSheet


class Card(QWidget):
    """ Example card """

    def __init__(self, title, widget, stretch=0, parent=None):
        super().__init__(parent=parent)
        if isinstance(widget, QLayout):
            self.widget = QWidget()
            self.widget.setLayout(widget)
        else:
            self.widget = widget
        self.stretch = stretch
        if title:
            self.title_layout = QHBoxLayout()
            self.titleLabel = StrongBodyLabel(title)
            self.titleLabel.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
            self.title_layout.addWidget(self.titleLabel)
            self.title_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        else:
            self.title_layout = None
        self.card = QFrame(self)
        if stretch == 1:
            self.card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.vBoxLayout = QVBoxLayout(self)
        self.cardLayout = QVBoxLayout(self.card)
        self.topLayout = QHBoxLayout()

        self.__initWidget()

    def __initWidget(self):
        self.__initLayout()
        self.card.setObjectName('card')

    def __initLayout(self):
        self.vBoxLayout.setSizeConstraint(QVBoxLayout.SetMinimumSize)
        self.cardLayout.setSizeConstraint(QVBoxLayout.SetMinimumSize)
        self.topLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.vBoxLayout.setSpacing(12)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.topLayout.setContentsMargins(12, 12, 12, 12)
        self.cardLayout.setContentsMargins(0, 0, 0, 0)
        if self.title_layout:
            self.vBoxLayout.addLayout(self.title_layout, 0)
        self.vBoxLayout.addWidget(self.card, 0, Qt.AlignTop)
        self.vBoxLayout.setAlignment(Qt.AlignTop)

        self.cardLayout.setSpacing(0)
        self.cardLayout.setAlignment(Qt.AlignTop)
        self.cardLayout.addLayout(self.topLayout, 0)

        self.widget.setParent(self.card)
        self.topLayout.addWidget(self.widget)
        StyleSheet.CARD.apply(self)
        # if self.stretch == 0:
        #     self.topLayout.addStretch(1)

        # self.widget.show()

    def add_top_widget(self, widget):
        self.title_layout.addWidget(widget)
