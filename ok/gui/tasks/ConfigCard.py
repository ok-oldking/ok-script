from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout
from qfluentwidgets import FluentIcon, ExpandSettingCard, PushButton

from ok import og
from ok.gui.common.design_system import DesignToken
from ok.gui.tasks.ConfigItemFactory import config_widget
from ok.gui.tasks.LabelAndWidget import LabelAndWidget


class ConfigContentMixin:
    def _init_config_content(self, task, config, default_config, config_description, config_type):
        self.config = config
        self.config_widgets = []
        self.config_widget_by_key = {}
        self.config_keys = []
        self.default_config = default_config
        self.config_description = config_description
        self.config_type = config_type
        self.sub_configs_rules = {}
        self.sub_configs_controlled_keys = {}
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
        self.viewLayout.setContentsMargins(6, 4, 6, 8)
        self.sub_configs_rules = self.__collect_sub_configs_rules()
        self.sub_configs_controlled_keys = self.__collect_sub_configs_controlled_keys()
        if not self.config or not (self.config.has_user_config() or self.default_config or self.config_type):
            self._on_empty_config_content()
        else:
            added_keys = set()
            for key, value in self.config.items():
                if not key.startswith('_') and not self.__is_hidden_config(key) and not self.__is_sub_config_key(key):
                    self.__addConfigWithSubConfigs(key, value, added_keys, set())
            if self.config_type:
                for key, the_type in self.config_type.items():
                    if key not in added_keys and not key.startswith('_') and not self.__is_hidden_config(key):
                        if self.__is_button_config(the_type) and not self.__is_sub_config_key(key):
                            self.__addConfigWithSubConfigs(key, None, added_keys, set())
        self.__setup_sub_configs()
        self.add_buttons()
        self._adjust_config_content_size()

    def _on_empty_config_content(self):
        pass

    def _adjust_config_content_size(self):
        if hasattr(self, '_adjustViewSize'):
            self._adjustViewSize()

    def __addConfigWithSubConfigs(self, key: str, value, added_keys, adding_keys):
        if key in added_keys or key in adding_keys:
            return

        adding_keys.add(key)
        self.__addConfig(key, value)
        added_keys.add(key)

        for sub_config_key in self.__get_sub_config_keys(key):
            if sub_config_key.startswith('_'):
                continue

            sub_config_value = self.__get_config_value(sub_config_key)
            if not self.__can_render_config(sub_config_key, sub_config_value):
                continue

            self.__addConfigWithSubConfigs(sub_config_key, sub_config_value, added_keys, adding_keys)

        adding_keys.remove(key)

    def __addConfig(self, key: str, value):
        widget = config_widget(self.config_type, self.config_description, self.config, key, value, self.task)
        self.config_widgets.append(widget)
        self.config_widget_by_key[key] = widget
        self.config_keys.append(key)
        if self.__is_sub_config_key(key):
            layout = widget.layout
            margins = layout.contentsMargins()
            layout.setContentsMargins(
                margins.left() + DesignToken.SUBCONFIG_INDENT,
                DesignToken.SUBCONFIG_TOP_PADDING,
                margins.right(), margins.bottom())
            widget.setMinimumHeight(DesignToken.SUBCONFIG_MIN_HEIGHT)
            widget.setProperty('subConfig', True)
        self.viewLayout.addWidget(widget)

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
            switch_button = getattr(widget, 'switch_button', None)
            if switch_button is not None:
                switch_button.checkedChanged.connect(self.__apply_sub_config_visibility)
            for check_box in getattr(widget, 'check_boxes', []):
                check_box.checkStateChanged.connect(self.__apply_sub_config_visibility)

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

    def __is_hidden_config(self, key):
        the_type = self.__get_config_type(key)
        return isinstance(the_type, dict) and the_type.get('hidden', False)

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
        config_keys = self.__resolve_sub_config_keys(
            self.sub_configs_rules.get(key, {}),
            self.config.get(key),
        )
        return [
            config_key for config_key in config_keys
            if config_key in self.config_widget_by_key
        ]

    def __resolve_sub_config_keys(self, rule, value):
        if not isinstance(value, list):
            try:
                return rule.get(value, [])
            except TypeError:
                return []

        config_keys = []
        for selected_value in value:
            try:
                selected_config_keys = rule.get(selected_value, [])
            except TypeError:
                continue
            for config_key in selected_config_keys:
                if config_key not in config_keys:
                    config_keys.append(config_key)
        return config_keys

    def __apply_sub_config_visibility(self, *args):
        self.__sync_sub_config_order()
        for key, widget in self.config_widget_by_key.items():
            widget.setVisible(self.__is_config_visible(key, set()))
        self._adjust_config_content_size()

    def __sync_sub_config_order(self):
        for widget in self.config_widget_by_key.values():
            self.viewLayout.removeWidget(widget)
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

        self.viewLayout.insertWidget(insert_index, self.config_widget_by_key[key])
        insert_index += 1

        for sub_config_key in active_sub_config_keys:
            insert_index = self.__insert_config_group(sub_config_key, insert_index, inserting_keys)

        inserting_keys.remove(key)
        return insert_index

    def __is_config_visible(self, key, checking):
        if key in checking:
            return False

        checking = checking | {key}
        for parent_key, rule in self.sub_configs_rules.items():
            if key not in self.sub_configs_controlled_keys.get(parent_key, set()):
                continue

            if not self.__is_config_visible(parent_key, checking):
                return False

            visible_config_keys = self.__resolve_sub_config_keys(rule, self.config.get(parent_key))

            if key not in visible_config_keys:
                return False

        return True

    def update_config(self):
        for widget in self.config_widgets:
            widget.update_value()
        self.__apply_sub_config_visibility()


class ConfigCard(ConfigContentMixin, ExpandSettingCard):
    def __init__(self, task, name, config, description, default_config, config_description,
                 config_type, config_icon):

        self._expand_enabled = True
        super().__init__(config_icon or FluentIcon.INFO, og.app.tr(name), og.app.tr(description))
        self._init_config_content(task, config, default_config, config_description, config_type)

    def setExpand(self, isExpand: bool):
        if isExpand and not self._expand_enabled:
            return
        if self.isExpand == isExpand:
            return

        content_height = self._visible_content_height()
        header_height = self.viewportMargins().top()
        target_height = header_height + content_height if isExpand else header_height
        parent = self.parentWidget()
        parent_updates_enabled = parent is not None and parent.updatesEnabled()
        if parent_updates_enabled:
            parent.setUpdatesEnabled(False)

        self.expandAni.stop()
        try:
            self.spaceWidget.hide()
            self.verticalScrollBar().setValue(0)
            self.isExpand = isExpand
            self.setProperty('isExpand', isExpand)
            self.setStyle(QApplication.style())
            self.card.expandButton.setExpand(isExpand)
            self.setFixedHeight(target_height)

            parent_layout = parent.layout() if parent is not None else None
            if parent_layout is not None:
                parent_layout.invalidate()
                parent_layout.activate()
        finally:
            if parent_updates_enabled:
                parent.setUpdatesEnabled(True)
                parent.update()

    def _adjustViewSize(self):
        """Resize to visible rows only; hidden sub-configs must not reserve space."""
        self.spaceWidget.hide()
        if self.isExpand:
            self.setFixedHeight(self.card.height() + self._visible_content_height())

    def _visible_content_height(self):
        margins = self.viewLayout.contentsMargins()
        self.viewLayout.activate()
        bottom = margins.top()
        for index in range(self.viewLayout.count()):
            item = self.viewLayout.itemAt(index)
            widget = item.widget()
            if widget is not None and widget.isHidden():
                continue

            bottom = max(bottom, item.geometry().bottom() + 1)
        return bottom + margins.bottom()

    def _on_empty_config_content(self):
        self._expand_enabled = False
        self.card.expandButton.hide()
