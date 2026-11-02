from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ok import og
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.tasks.config_form import ConfigForm


def _app_tr(text):
    return og.app.tr(text) if og.app is not None and text else (text or "")


class ConfigSection(QWidget):
    """One global config option: its name, description, Reset and settings form."""

    def __init__(self, config, option, title_role: str = "subtitle", parent=None):
        super().__init__(parent)
        self.config = config
        self.option = option
        self.title_label = Label(_app_tr(option.name), title_role, self)
        self.description_label = Label(_app_tr(option.description), "secondary", self, word_wrap=True)
        self.description_label.setVisible(bool(option.description))
        self.form = ConfigForm(None, config, option.default_config, option.config_description, option.config_type,
                               self)
        self.reset_button = Button(QCoreApplication.translate("ConfigCard", "Reset Config"), "reset", "subtle",
                                   "small", parent=self)
        self.reset_button.clicked.connect(self.reset_clicked)
        self.reset_button.setVisible(bool(option.default_config) and not self.form.is_empty)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)
        header.addWidget(self.title_label, 1)
        header.addWidget(self.reset_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addWidget(self.description_label)
        layout.addSpacing(4)
        layout.addWidget(self.form)

    @property
    def config_widget_by_key(self):
        return self.form.config_widget_by_key

    def has_key(self, key) -> bool:
        return key in self.config

    def reset_clicked(self) -> None:
        self.config.reset_to_default()
        self.form.update_config()
