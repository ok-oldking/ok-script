from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ok.ui.qt.kit.cards import Card, SettingRow
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.tasks.ConfigCard import ConfigContentMixin
from ok.ui.qt.tasks.config_editors import config_editor


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
