from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ok import og
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.tasks.config_form import ConfigForm

OTHER_GROUP = 'Other'


def _app_tr(text):
    return og.app.tr(text) if og.app is not None and text else (text or "")


def _type_of(config_type, key):
    the_type = (config_type or {}).get(key)
    return the_type if isinstance(the_type, dict) else {}


def group_config_keys(config, config_type):
    """Split an option's keys into ``[(group, keys)]`` from ``config_type[key]['group']``.

    Groups keep the order of their first key; rows shown for another row's value
    follow that row's group, and ungrouped keys go to a trailing "Other" group.
    Returns None when no key names a group, so the option renders as one form.
    """
    config_type = config_type or {}
    keys = [key for key in list(config) + list(config_type) if not str(key).startswith('_')]
    keys = list(dict.fromkeys(keys))
    if not any(_type_of(config_type, key).get('group') for key in keys):
        return None

    parent_of = {}
    for key in keys:
        sub_configs = _type_of(config_type, key).get('sub_configs')
        if isinstance(sub_configs, dict):
            for children in sub_configs.values():
                for child in [children] if isinstance(children, str) else (children or []):
                    parent_of.setdefault(child, key)

    def group_of(key, seen=()):
        group = _type_of(config_type, key).get('group')
        if group:
            return group
        parent = parent_of.get(key)
        if parent is not None and parent not in seen:
            return group_of(parent, seen + (key,))
        return OTHER_GROUP

    groups = {}
    for key in keys:
        groups.setdefault(group_of(key), []).append(key)
    if OTHER_GROUP in groups:
        groups[OTHER_GROUP] = groups.pop(OTHER_GROUP)
    return list(groups.items())


def _group_config_type(config_type, all_keys, group_keys):
    """The option's config_type with every key outside ``group_keys`` hidden."""
    filtered = dict(config_type or {})
    for key in all_keys:
        if key not in group_keys:
            filtered[key] = {'hidden': True}
    return filtered


class ConfigSection(QWidget):
    """One global config option: its name, description, Reset and settings forms.

    Keys whose ``config_type`` names a ``group`` render as one titled card per
    group; otherwise all keys share a single card. With ``group`` and ``keys``
    the section shows only that group, titled by it, and Reset restores only
    its keys.
    """

    def __init__(self, config, option, title_role: str = "subtitle", parent=None, group=None, keys=None,
                 show_description=True):
        super().__init__(parent)
        self.config = config
        self.option = option
        self.group = group
        self.keys = list(keys) if keys is not None else None
        self.title_label = Label(_app_tr(group if group is not None else option.name), title_role, self)
        self.description_label = Label(_app_tr(option.description), "secondary", self, word_wrap=True)
        self.description_label.setVisible(bool(option.description) and show_description)
        self.forms = []
        self.group_widgets = {}
        groups = group_config_keys(config, option.config_type) if self.keys is None else None
        if self.keys is not None:
            all_keys = [key for _, group_keys in group_config_keys(config, option.config_type) or []
                        for key in group_keys]
            self.form = self._create_form(_group_config_type(option.config_type, all_keys, set(self.keys)))
            body = self.form
        elif groups is None:
            self.form = self._create_form(option.config_type)
            body = self.form
        else:
            all_keys = [key for _, keys in groups for key in keys]
            body = QWidget(self)
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(20)
            for group, keys in groups:
                form = self._create_form(_group_config_type(option.config_type, all_keys, set(keys)))
                if form.is_empty:
                    # Every row in this group is hidden.
                    form.deleteLater()
                    self.forms.remove(form)
                    continue
                group_widget = QWidget(body)
                group_layout = QVBoxLayout(group_widget)
                group_layout.setContentsMargins(0, 0, 0, 0)
                group_layout.setSpacing(8)
                group_layout.addWidget(Label(_app_tr(group), "section", group_widget))
                group_layout.addWidget(form)
                body_layout.addWidget(group_widget)
                self.group_widgets[group] = group_widget
            if not self.forms:
                body_layout.addWidget(self._create_form(option.config_type))
            self.form = self.forms[0]
        self.reset_button = Button(QCoreApplication.translate("ConfigCard", "Reset Config"), "reset", "subtle",
                                   "small", parent=self)
        self.reset_button.clicked.connect(self.reset_clicked)
        has_defaults = (bool(option.default_config) if self.keys is None
                        else any(key in option.default_config for key in self.keys))
        self.reset_button.setVisible(has_defaults and not self.is_empty)

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
        layout.addWidget(body)

    def _create_form(self, config_type):
        form = ConfigForm(None, self.config, self.option.default_config, self.option.config_description,
                          config_type, self)
        self.forms.append(form)
        return form

    @property
    def is_empty(self) -> bool:
        return all(form.is_empty for form in self.forms)

    @property
    def config_widget_by_key(self):
        widgets = {}
        for form in self.forms:
            widgets.update(form.config_widget_by_key)
        return widgets

    def has_key(self, key) -> bool:
        if self.keys is not None:
            return key in self.keys
        return key in self.config

    def reset_clicked(self) -> None:
        if self.keys is None:
            self.config.reset_to_default()
        else:
            for key in self.keys:
                if key in self.option.default_config:
                    self.config[key] = self.option.default_config[key]
        for form in self.forms:
            form.update_config()
