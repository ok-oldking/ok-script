from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ok.ui.qt.kit.cards import Card, SettingRow
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.tasks.config_editors import config_editor


class ConfigContentMixin:
    """Builds config rows into ``self.viewLayout`` and shows sub-config rows for matching values."""

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
        """Hook for actions below the rows; the form has none."""

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

    def _create_config_widget(self, key, value):
        raise NotImplementedError

    def _mark_sub_config(self, widget):
        """Hook to style a row shown only for another row's value."""

    def __addConfig(self, key: str, value):
        widget = self._create_config_widget(key, value)
        self.config_widgets.append(widget)
        self.config_widget_by_key[key] = widget
        self.config_keys.append(key)
        if self.__is_sub_config_key(key):
            self._mark_sub_config(widget)
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
            # Editors announce every edit through one signal.
            if widget is not None:
                widget.value_changed.connect(self.__apply_sub_config_visibility)

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


class ConfigForm(ConfigContentMixin, QWidget):
    """A task's settings as kit rows in one card.

    Sub-config rules (rows shown only for certain values of another row) and
    their ordering come from :class:`ConfigContentMixin`; actions such as
    resetting the config live with the caller, not in the form.
    """

    def __init__(self, task, config, default_config, config_description, config_type, parent=None):
        QWidget.__init__(self, parent)
        self.setObjectName("scrollContents")
        self.is_empty = False
        self.card = Card(look="inset")
        self.viewLayout = QVBoxLayout(self.card)
        self.empty_label = Label(QCoreApplication.translate("TaskDetail", "This task has no settings."), "secondary")
        self.empty_label.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.card)
        layout.addWidget(self.empty_label)
        layout.addStretch(1)
        self._init_config_content(task, config, default_config, config_description, config_type)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        if not self.config_widgets and not self.is_empty:
            # Only hidden or private keys: nothing to edit.
            self._on_empty_config_content()

    def _create_config_widget(self, key, value):
        return config_editor(self.config_type, self.config_description, self.config, key, value, self.task)

    def _mark_sub_config(self, widget):
        widget.set_indent(True)

    def add_buttons(self):
        pass

    def _on_empty_config_content(self):
        self.is_empty = True
        self.card.hide()
        self.empty_label.show()

    def _adjust_config_content_size(self):
        # Only the first visible row drops its top divider.
        first = True
        for index in range(self.viewLayout.count()):
            widget = self.viewLayout.itemAt(index).widget()
            if isinstance(widget, SettingRow) and not widget.isHidden():
                widget.set_first(first)
                first = False
