from PySide6.QtWidgets import QWidget, QLabel, QSpacerItem, QSizePolicy, QHBoxLayout, QVBoxLayout, QLayout


class LabelAndWidget(QWidget):

    def __init__(self, title: str, content=None):
        super().__init__()
        from ok.gui import app
        self.layout = QHBoxLayout(self)
        self.title_layout = QVBoxLayout()
        self.layout.addLayout(self.title_layout)
        self.title = QLabel(app.tr(title))
        self.title.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.title_layout.addWidget(self.title)
        if content:
            self.contentLabel = QLabel(app.tr(content))
            self.contentLabel.setObjectName('contentLabel')
            self.title_layout.addWidget(self.contentLabel)
        self.layout.addItem(QSpacerItem(20, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

    def add_widget(self, widget: QWidget, stretch=0):
        self.layout.addWidget(widget, stretch=stretch)

    def add_layout(self, layout: QLayout, stretch=0):
        self.layout.addLayout(layout, stretch=stretch)
