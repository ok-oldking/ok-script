from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout
from ok.gui.tasks.LabelAndWidget import LabelAndWidget
from qfluentwidgets import FluentIcon, ExpandSettingCard, PushButton

from ok import og
from ok.gui.tasks.ConfigItemFactory import config_widget


class ConfigCard(ExpandSettingCard):
    def __init__(self, task, name, config, description, default_config, config_description,
                 config_type, config_icon):

        super().__init__(config_icon or FluentIcon.INFO, og.app.tr(name), og.app.tr(description))
        self.config = config
        self.config_widgets = []
        self.default_config = default_config
        self.config_description = config_description
        self.config_type = config_type
        self.task = task
        self.reset_config = None
        self.__initWidget()

    def reset_clicked(self):
        self.config.reset_to_default()
        self.update_config()

    def add_buttons(self):
        if self.default_config or (self.task and self.task.show_create_shortcut):
            layout = LabelAndWidget(self.tr('Operation'))
            buttons_layout = QHBoxLayout()
            buttons_layout.addStretch(1)
            layout.add_layout(buttons_layout)
            self.viewLayout.addWidget(layout)

            if self.default_config:
                self.reset_config = PushButton(FluentIcon.CANCEL, self.tr("Reset Config"))
                buttons_layout.addWidget(self.reset_config)
                self.reset_config.clicked.connect(self.reset_clicked)

            if self.task and self.task.show_create_shortcut:
                create_shortcut = PushButton(FluentIcon.LINK, self.tr("Add Start Menu Shortcut"))
                buttons_layout.addWidget(create_shortcut)
                create_shortcut.clicked.connect(self.task.create_shortcut)

    def __initWidget(self):
        # initialize layout
        self.viewLayout.setSpacing(0)
        self.viewLayout.setAlignment(Qt.AlignTop)
        self.viewLayout.setContentsMargins(10, 0, 10, 0)
        if not self.config or not self.config.has_user_config() and not self.default_config:
            self.card.expandButton.hide()
        else:
            for key, value in self.config.items():
                if not key.startswith('_'):
                    self.__addConfig(key, value)
        self.add_buttons()
        self._adjustViewSize()

    def __addConfig(self, key: str, value):
        widget = config_widget(self.config_type, self.config_description, self.config, key, value, self.task)
        self.config_widgets.append(widget)
        self.viewLayout.addWidget(widget)


    def update_config(self):
        for widget in self.config_widgets:
            widget.update_value()
