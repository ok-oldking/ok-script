from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import FluentIcon, ExpandSettingCard, PushButton
from ok import og
from ok.gui.tasks.ConfigItemFactory import config_widget
from ok.gui.tasks.ConfigGroupWidget import ConfigGroupWidget, collect_group_children, valid_group_child_keys
from ok.gui.tasks.LabelAndWidget import LabelAndWidget


class ConfigCard(ExpandSettingCard):
    def __init__(self, task, name, config, description, default_config, config_description, config_type, config_icon, config_group=None):
        super().__init__(config_icon or FluentIcon.INFO, og.app.tr(name), og.app.tr(description))
        self.config = config
        self.config_widgets = []
        self.default_config = default_config
        self.config_description = config_description
        self.config_type = config_type
        self.config_group = config_group or {}
        self.task = task
        self.reset_config = None
        self.__initWidget()

    def reset_clicked(self):
        self.config.reset_to_default()
        self.update_config()

    def add_buttons(self):
        if self.default_config or (self.task and self.task.show_create_shortcut):
            layout = LabelAndWidget(self.tr("Operation"))
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
        if not self.config or not (self.config.has_user_config() or self.default_config or self.config_type):
            self.card.expandButton.hide()
        else:
            added_keys = set()
            group_children = collect_group_children(self.config, self.config_group)
            for key, value in self.config.items():
                if not key.startswith("_") and key not in group_children:
                    add_to_view = key not in self.config_group
                    parent_widget = self.__addConfig(key, value, add_to_view=add_to_view)
                    added_keys.add(key)
                    self.__add_grouped_children(key, parent_widget, added_keys)
            if self.config_type:
                for key, the_type in self.config_type.items():
                    if key not in added_keys and key not in group_children and not key.startswith("_"):
                        if isinstance(the_type, dict) and the_type.get("type") == "button":
                            self.__addConfig(key, None)
        self.add_buttons()
        self._adjustViewSize()

    def __addConfig(self, key: str, value, add_to_view=True):
        widget = config_widget(self.config_type, self.config_description, self.config, key, value, self.task)
        self.config_widgets.append(widget)
        if add_to_view:
            self.viewLayout.addWidget(widget)
        return widget

    def __add_grouped_children(self, parent_key: str, parent_widget, added_keys: set):
        child_keys = valid_group_child_keys(self.config_group.get(parent_key), self.config, added_keys)
        if not child_keys:
            return

        group_widget = ConfigGroupWidget(parent_widget, self.tr("Toggle options"), self._adjustViewSize, self)
        for child_key in child_keys:
            child_widget = self.__addConfig(child_key, self.config.get(child_key), add_to_view=False)
            group_widget.add_child_widget(child_widget)
            added_keys.add(child_key)
        self.viewLayout.addWidget(group_widget)

    def update_config(self):
        for widget in self.config_widgets:
            widget.update_value()
