from PySide6.QtWidgets import QWidget, QSizePolicy, QHBoxLayout, QVBoxLayout, QLayout, QLabel


class LabelAndWidget(QWidget):

    def __init__(self, title: str, content=None):
        super().__init__()
        from ok import og
        self.layout = QHBoxLayout(self)
        self.title_layout = QVBoxLayout()
        self.layout.addLayout(self.title_layout, stretch=0)
        self.title = QLabel(og.app.tr(title))
        # self.title.setWordWrap(True)
        self.title.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.title_layout.addWidget(self.title)
        self.title.setObjectName('titleLabel')
        if content:
            self.contentLabel = QLabel(og.app.tr(content))
            self.contentLabel.setObjectName('contentLabel')
            self.title_layout.addWidget(self.contentLabel)
        self.layout.addStretch()

    def add_widget(self, widget: QWidget, stretch=1):
        self.layout.addWidget(widget, stretch=stretch)

    def add_layout(self, layout: QLayout, stretch=1):
        self.layout.addLayout(layout, stretch=stretch)
