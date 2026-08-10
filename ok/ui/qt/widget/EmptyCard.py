from PySide6.QtWidgets import QWidget, QFrame

from ok.gui.common.style_sheet import StyleSheet


class EmptyCard(QWidget):
    """ Example card """

    def __init__(self, layout, parent=None):
        super().__init__(parent=parent)
        self.card = QFrame(self)
        self.setLayout(layout)
        StyleSheet.TAB.apply(self)
        self.card.setObjectName('card')
