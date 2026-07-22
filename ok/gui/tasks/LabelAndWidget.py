from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QSizePolicy, QHBoxLayout, QVBoxLayout, QLayout, QLabel

from ok.gui.common.design_system import configure_row


class LabelAndWidget(QWidget):

    def __init__(self, title: str, content=None):
        super().__init__()
        from ok import og
        self.layout = QHBoxLayout(self)
        configure_row(self, self.layout)
        self.title_layout = QVBoxLayout()
        self.title_layout.setContentsMargins(0, 0, 0, 0)
        self.title_layout.setSpacing(2)
        self.layout.addLayout(self.title_layout, stretch=0)
        translated_title = og.app.tr(title)
        if '{app_name}' in translated_title:
            translated_title = translated_title.format(app_name=(og.config or {}).get('gui_title', ''))
        self.title = QLabel(translated_title)
        # self.title.setWordWrap(True)
        self.title.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.title_layout.addWidget(self.title)
        self.title.setObjectName('titleLabel')
        if content:
            self.contentLabel = QLabel(og.app.tr(content))
            self.contentLabel.setObjectName('contentLabel')
            self.contentLabel.setWordWrap(True)
            self.title_layout.addWidget(self.contentLabel)
        self.title_layout.setAlignment(Qt.AlignVCenter)
        self.layout.addStretch()

    def add_widget(self, widget: QWidget, stretch=1):
        self.layout.addWidget(widget, stretch=stretch)

    def add_layout(self, layout: QLayout, stretch=1):
        self.layout.addLayout(layout, stretch=stretch)
