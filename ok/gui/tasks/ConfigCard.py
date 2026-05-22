from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout
from qfluentwidgets import FluentIcon, ExpandSettingCard, PushButton

from ok import og
from ok.gui.tasks.ConfigItemFactory import config_widget
from ok.gui.tasks.LabelAndWidget import LabelAndWidget


class ConfigCard(ExpandSettingCard):
    def __init__(self, task, name, config, description, default_config, config_description,
                 config_type, config_icon):

        super().__init__(config_icon or FluentIcon.INFO, og.app.tr(name), og.app.tr(description))
        self.config = config
        self.config_widgets = []
        self.config_widget_by_key = {}
        self.config_keys = []
        self.default_config = default_config
        self.config_description = config_description
        self.config_type = config_type
        self.sub_configs_rules = {}
        self.sub_configs_controlled_keys = {}
        self.sub_configs_dividers = {}
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
        self.sub_configs_rules = self.__collect_sub_configs_rules()
        self.sub_configs_controlled_keys = self.__collect_sub_configs_controlled_keys()
        if not self.config or not (self.config.has_user_config() or self.default_config or self.config_type):
            self.card.expandButton.hide()
        else:
            added_keys = set()
            for key, value in self.config.items():
                if not key.startswith('_') and not self.__is_sub_config_key(key):
                    self.__addConfigWithSubConfigs(key, value, added_keys, set())
            if self.config_type:
                for key, the_type in self.config_type.items():
                    if key not in added_keys and not key.startswith('_'):
                        if self.__is_button_config(the_type) and not self.__is_sub_config_key(key):
                            self.__addConfigWithSubConfigs(key, None, added_keys, set())
        self.__setup_sub_configs()
        self.add_buttons()
        self._adjustViewSize()

    def __addConfigWithSubConfigs(self, key: str, value, added_keys, adding_keys):
        if key in added_keys or key in adding_keys:
            return

        adding_keys.add(key)
        has_sub_configs = self.__has_renderable_sub_configs(key)
        if has_sub_configs:
            self.__add_sub_configs_divider(key, 'top')

        self.__addConfig(key, value)
        added_keys.add(key)

        for sub_config_key in self.__get_sub_config_keys(key):
            if sub_config_key.startswith('_'):
                continue

            sub_config_value = self.__get_config_value(sub_config_key)
            if not self.__can_render_config(sub_config_key, sub_config_value):
                continue

            self.__addConfigWithSubConfigs(sub_config_key, sub_config_value, added_keys, adding_keys)

        if has_sub_configs:
            self.__add_sub_configs_divider(key, 'bottom')

        adding_keys.remove(key)

    def __addConfig(self, key: str, value):
        widget = config_widget(self.config_type, self.config_description, self.config, key, value, self.task)
        self.config_widgets.append(widget)
        self.config_widget_by_key[key] = widget
        self.config_keys.append(key)
        self.viewLayout.addWidget(widget)

    def __add_sub_configs_divider(self, key, position):
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Plain)
        divider.setObjectName('subConfigsDivider')
        divider.setFixedHeight(1)
        divider.setStyleSheet("color: rgba(128, 128, 128, 90); background-color: rgba(128, 128, 128, 90);")
        self.sub_configs_dividers.setdefault(key, {})[position] = divider
        self.viewLayout.addWidget(divider)

    def __is_button_config(self, the_type):
        return (
            isinstance(the_type, dict)
            and (
                the_type.get('type') == 'button'
                or ('type' not in the_type and ('buttons' in the_type or 'callback' in the_type))
            )
        )

    def __setup_sub_configs(self):
        if not self.sub_configs_rules:
            return

        for key in self.sub_configs_rules:
            widget = self.config_widget_by_key.get(key)
            combo_box = getattr(widget, 'combo_box', None)
            if combo_box is not None:
                combo_box.currentTextChanged.connect(self.__apply_sub_config_visibility)

        self.__apply_sub_config_visibility()

    def __collect_sub_configs_rules(self):
        rules = {}
        if not self.config_type:
            return rules

        for key, the_type in self.config_type.items():
            if not isinstance(the_type, dict):
                continue

            sub_configs = the_type.get('sub_configs')
            if not isinstance(sub_configs, dict):
                continue

            rules[key] = {
                choice: self.__normalize_sub_config_keys(config_keys)
                for choice, config_keys in sub_configs.items()
            }

        return rules

    def __collect_sub_configs_controlled_keys(self):
        return {
            key: set().union(*rule.values()) if rule else set()
            for key, rule in self.sub_configs_rules.items()
        }

    def __normalize_sub_config_keys(self, config_keys):
        if config_keys is None:
            return []
        if isinstance(config_keys, str):
            return [config_keys]
        return list(config_keys)

    def __is_sub_config_key(self, key):
        return any(key in keys for keys in self.sub_configs_controlled_keys.values())

    def __get_config_type(self, key):
        if self.config_type is None:
            return None
        return self.config_type.get(key)

    def __get_config_value(self, key):
        if self.config is not None and key in self.config:
            return self.config.get(key)
        return None

    def __can_render_config(self, key, value):
        return value is not None or self.__is_button_config(self.__get_config_type(key))

    def __has_renderable_sub_configs(self, key):
        for sub_config_key in self.__get_sub_config_keys(key):
            if sub_config_key.startswith('_'):
                continue
            if self.__can_render_config(sub_config_key, self.__get_config_value(sub_config_key)):
                return True
        return False

    def __get_sub_config_keys(self, key):
        keys = []
        for config_keys in self.sub_configs_rules.get(key, {}).values():
            for config_key in config_keys:
                if config_key not in keys:
                    keys.append(config_key)
        return keys

    def __get_active_sub_config_keys(self, key):
        try:
            config_keys = self.sub_configs_rules.get(key, {}).get(self.config.get(key), [])
        except TypeError:
            return []
        return [
            config_key for config_key in config_keys
            if config_key in self.config_widget_by_key
        ]

    def __apply_sub_config_visibility(self, *args):
        self.__sync_sub_config_order()
        for key, widget in self.config_widget_by_key.items():
            widget.setVisible(self.__is_config_visible(key, set()))
        for key, dividers in self.sub_configs_dividers.items():
            visible = self.__is_sub_configs_group_visible(key)
            for divider in dividers.values():
                divider.setVisible(visible)
        self._adjustViewSize()

    def __sync_sub_config_order(self):
        for widget in self.config_widget_by_key.values():
            self.viewLayout.removeWidget(widget)
        for dividers in self.sub_configs_dividers.values():
            for divider in dividers.values():
                self.viewLayout.removeWidget(divider)

        insert_index = 0
        for key in self.config_keys:
            if self.__is_sub_config_key(key):
                continue
            insert_index = self.__insert_config_group(key, insert_index, set())

    def __insert_config_group(self, key, insert_index, inserting_keys):
        if key in inserting_keys or key not in self.config_widget_by_key:
            return insert_index

        inserting_keys.add(key)
        active_sub_config_keys = self.__get_active_sub_config_keys(key)
        has_visible_sub_configs = any(
            self.__is_config_visible(sub_config_key, set())
            for sub_config_key in active_sub_config_keys
        )

        if has_visible_sub_configs:
            insert_index = self.__insert_sub_configs_divider(key, 'top', insert_index)

        self.viewLayout.insertWidget(insert_index, self.config_widget_by_key[key])
        insert_index += 1

        for sub_config_key in active_sub_config_keys:
            insert_index = self.__insert_config_group(sub_config_key, insert_index, inserting_keys)

        if has_visible_sub_configs:
            insert_index = self.__insert_sub_configs_divider(key, 'bottom', insert_index)

        inserting_keys.remove(key)
        return insert_index

    def __insert_sub_configs_divider(self, key, position, insert_index):
        divider = self.sub_configs_dividers.get(key, {}).get(position)
        if divider is None:
            return insert_index

        self.viewLayout.insertWidget(insert_index, divider)
        return insert_index + 1

    def __is_sub_configs_group_visible(self, key):
        if not self.__is_config_visible(key, set()):
            return False
        for sub_config_key in self.__get_active_sub_config_keys(key):
            if sub_config_key in self.config_widget_by_key and self.__is_config_visible(sub_config_key, set()):
                return True
        return False

    def __is_config_visible(self, key, checking):
        if key in checking:
            return False

        checking = checking | {key}
        for parent_key, rule in self.sub_configs_rules.items():
            if key not in self.sub_configs_controlled_keys.get(parent_key, set()):
                continue

            if not self.__is_config_visible(parent_key, checking):
                return False

            try:
                visible_config_keys = rule.get(self.config.get(parent_key), [])
            except TypeError:
                visible_config_keys = []

            if key not in visible_config_keys:
                return False

        return True

    def update_config(self):
        for widget in self.config_widgets:
            widget.update_value()
        self.__apply_sub_config_visibility()
