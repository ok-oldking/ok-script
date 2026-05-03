from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import FluentIcon, ExpandSettingCard, PushButton
from ok import og
from ok.gui.tasks.ConfigItemFactory import config_widget
from ok.gui.tasks.ConfigGroupWidget import ConfigGroupWidget, collect_group_children
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
            group_children = collect_group_children(self.config_group)
            for key, value in self.config.items():
                if not key.startswith("_") and key not in group_children:
                    add_to_view = key not in self.config_group
                    parent_widget = self.__addConfig(key, value, add_to_view=add_to_view)
                    added_keys.add(key)
                    if key in self.config_group and not self.__add_grouped_children(key, parent_widget, added_keys):
                        self.viewLayout.addWidget(parent_widget)
            ConfigGroupWidget.add_title_only_groups(self.viewLayout, self.config_group, self.config, added_keys,
                                                    self.__addConfig, on_height_changed=self._adjustViewSize,
                                                    parent=self, toggle_tooltip=self.tr("Toggle options"))
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
        nested = ConfigGroupWidget.build_group_widget(parent_key, parent_widget, self.config, self.config_group,
                                                      added_keys, self.__addConfig,
                                                      on_height_changed=self._adjustViewSize, parent=self,
                                                      toggle_tooltip=self.tr("Toggle options"))
        if not nested:
            return False
        self.viewLayout.addWidget(nested)
        return True

    def update_config(self):
        for widget in self.config_widgets:
            widget.update_value()
