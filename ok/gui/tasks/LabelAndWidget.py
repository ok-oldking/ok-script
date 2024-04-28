from PySide6.QtWidgets import QWidget, QLabel, QSpacerItem, QSizePolicy, QHBoxLayout, QVBoxLayout


class LabelAndWidget(QWidget):

    def __init__(self, title: str, content=None):
        super().__init__()
        self.layout = QHBoxLayout(self)
        self.title_layout = QVBoxLayout()
        self.layout.addLayout(self.title_layout)
        self.title = QLabel(title)
        self.title.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.title_layout.addWidget(self.title)
        if content:
            self.contentLabel = QLabel(content)
            self.contentLabel.setObjectName('contentLabel')
            self.title_layout.addWidget(self.contentLabel)
        self.layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

    def add_widget(self, widget: QWidget):
        self.layout.addWidget(widget)
