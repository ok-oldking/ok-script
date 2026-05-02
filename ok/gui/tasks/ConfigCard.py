from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget, QVBoxLayout
from qfluentwidgets import FluentIcon, ExpandSettingCard, PushButton

from ok import og
from ok.gui.tasks.ConfigItemFactory import config_widget
from ok.gui.tasks.LabelAndWidget import LabelAndWidget


class ConfigCard(ExpandSettingCard):
    def __init__(self, task, name, config, description, default_config, config_description,
                 config_type, config_icon, config_group=None):

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
        if not self.config or not (self.config.has_user_config() or self.default_config or self.config_type):
            self.card.expandButton.hide()
        else:
            added_keys = set()
            group_children = self.__collect_group_children()
            for key, value in self.config.items():
                if not key.startswith('_') and key not in group_children:
                    parent_widget = self.__addConfig(key, value)
                    added_keys.add(key)
                    self.__add_grouped_children(key, parent_widget, added_keys)
            if self.config_type:
                for key, the_type in self.config_type.items():
                    if key not in added_keys and key not in group_children and not key.startswith('_'):
                        if isinstance(the_type, dict) and the_type.get('type') == 'button':
                            self.__addConfig(key, None)
        self.add_buttons()
        self._adjustViewSize()

    def __addConfig(self, key: str, value, add_to_view=True):
        widget = config_widget(self.config_type, self.config_description, self.config, key, value, self.task)
        self.config_widgets.append(widget)
        if add_to_view:
            self.viewLayout.addWidget(widget)
        return widget

    def __collect_group_children(self):
        children = set()
        for _, grouped in self.config_group.items():
            if isinstance(grouped, (list, tuple)):
                for child_key in grouped:
                    if isinstance(child_key, str):
                        children.add(child_key)
        return children

    def __add_grouped_children(self, parent_key: str, parent_widget, added_keys: set):
        children = self.config_group.get(parent_key)
        if not isinstance(children, (list, tuple)) or len(children) == 0:
            return

        toggle_button = PushButton(self.tr('Options'))
        toggle_button.setFixedHeight(30)
        parent_widget.add_widget(toggle_button, stretch=0)

        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(24, 0, 0, 0)
        panel_layout.setSpacing(0)
        panel.setVisible(False)

        def toggle_panel():
            expanded = not panel.isVisible()
            panel.setVisible(expanded)
            toggle_button.setText(self.tr('Options') + (' ▴' if expanded else ' ▾'))
            self._adjustViewSize()

        toggle_button.clicked.connect(toggle_panel)
        toggle_button.setText(self.tr('Options') + ' ▾')

        added_child = False
        for child_key in children:
            if not isinstance(child_key, str):
                continue
            if child_key.startswith('_') or child_key in added_keys or child_key not in self.config:
                continue
            child_widget = self.__addConfig(child_key, self.config.get(child_key), add_to_view=False)
            panel_layout.addWidget(child_widget)
            added_keys.add(child_key)
            added_child = True

        if added_child:
            self.viewLayout.addWidget(panel)
        else:
            toggle_button.hide()


    def update_config(self):
        for widget in self.config_widgets:
            widget.update_value()
