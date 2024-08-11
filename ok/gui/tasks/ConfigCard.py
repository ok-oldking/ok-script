from PySide6.QtCore import Qt
from qfluentwidgets import FluentIcon, ExpandSettingCard, PushButton

from ok.gui.tasks.ConfigItemFactory import config_widget


class ConfigCard(ExpandSettingCard):
    def __init__(self, name, config, description, default_config, config_description,
                 config_type, config_icon):
        from ok.gui import app
        super().__init__(config_icon or FluentIcon.INFO, app.tr(name), app.tr(description))
        self.config = config
        self.config_widgets = []
        self.default_config = default_config
        self.config_description = config_description
        self.config_type = config_type
        if default_config:
            self.reset_config = PushButton(FluentIcon.CANCEL, self.tr("Reset Config"), self)
            self.addWidget(self.reset_config)
            self.reset_config.clicked.connect(self.reset_clicked)
        self.__initWidget()

    def reset_clicked(self):
        self.config.reset_to_default()
        self.update_config()

    def __initWidget(self):
        # initialize layout
        self.viewLayout.setSpacing(0)
        self.viewLayout.setAlignment(Qt.AlignTop)
        self.viewLayout.setContentsMargins(10, 0, 10, 0)
        if not self.config or not self.config.has_user_config():
            self.card.expandButton.hide()
        else:
            for key, value in self.config.items():
                if not key.startswith('_'):
                    self.__addConfig(key, value)

    def __addConfig(self, key: str, value):
        widget = config_widget(self.config_type, self.config_description, self.config, key, value)
        self.config_widgets.append(widget)
        self.viewLayout.addWidget(widget)
        self._adjustViewSize()

    def update_config(self):
        for widget in self.config_widgets:
            widget.update_value()
