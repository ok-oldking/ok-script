from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from ok import Config, ConfigOption
from ok.ui.qt.kit.theme import theme
from ok.ui.qt.settings.config_section import ConfigSection


class GlobalConfigTab(QWidget):
    """A global config option shown as its own page (``show_at_tab``)."""

    def __init__(self, config: Config, option: ConfigOption, parent=None):
        super().__init__(parent)
        self.config = config
        self.option = option
        self.section = ConfigSection(config, option, title_role="display")

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        contents = QWidget()
        contents.setObjectName("scrollContents")
        column = QVBoxLayout(contents)
        column.setContentsMargins(28, 20, 28, 28)
        column.addWidget(self.section)
        column.addStretch(1)
        scroll.setWidget(contents)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)
        theme.install(self)

    @property
    def config_widget_by_key(self):
        return self.section.config_widget_by_key

    def has_key(self, key) -> bool:
        return self.section.has_key(key)

    def reset_clicked(self) -> None:
        self.section.reset_clicked()
