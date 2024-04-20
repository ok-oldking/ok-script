from PySide6.QtWidgets import QWidget, QLabel, QSpacerItem, QSizePolicy, QHBoxLayout


class LabelAndWidget(QWidget):

    def __init__(self, title: str):
        super().__init__()
        self.layout = QHBoxLayout(self)
        self.title = QLabel(title)
        self.title.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.layout.addWidget(self.title)
        self.layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

    def add_widget(self, widget: QWidget):
        self.layout.addWidget(widget)
