"""Kit editors for task config values.

Each editor is a :class:`SettingRow` bound to one key of a ``Config``. It
writes edits back to the config, reloads itself in :meth:`update_value`, and
emits ``value_changed`` so dependent sub-configs can show or hide.
``config_editor`` picks the editor from the config type and default value,
following the same rules as the older ``ConfigItemFactory``.
"""

import os

from PySide6.QtCore import QCoreApplication, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QCheckBox, QFileDialog, QHBoxLayout, QLineEdit, QPlainTextEdit, QWidget

from ok import og
from ok.core.config_schema import resolve_config_type
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.cards import CONTROL_COLUMN, SettingRow
from ok.ui.qt.kit.dialogs import Dialog
from ok.ui.qt.kit.inputs import ComboBox, NumberBox
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.layout import FlowLayout
from ok.ui.qt.kit.switch import Switch
from ok.ui.qt.shell.nav_icons import nav_icon
from ok.ui.qt.widget.UpdateConfigWidgetItem import value_to_string


def _t(context: str, text: str) -> str:
    return QCoreApplication.translate(context, text)


def _app_tr(text):
    return og.app.tr(text) if og.app is not None else text


def config_title(key: str) -> str:
    title = _app_tr(key)
    if '{app_name}' in title:
        title = title.format(app_name=(og.config or {}).get('gui_title', ''))
    return title


class ConfigEditor(SettingRow):
    """A setting row bound to ``config[key]``."""

    value_changed = Signal(object)

    def __init__(self, config_desc, config, key: str, control: QWidget = None, control_width: int = CONTROL_COLUMN):
        description = config_desc.get(key) if config_desc else None
        super().__init__(config_title(key), _app_tr(description) if description else None,
                         control_width=control_width)
        self.key = key
        self.config = config
        if control is not None:
            self.set_control(control)

    def update_config(self, value) -> None:
        self.config[self.key] = value
        self.value_changed.emit(value)

    def update_value(self) -> None:
        pass


class SwitchEditor(ConfigEditor):
    def __init__(self, config_desc, config, key):
        self.switch_button = Switch()
        super().__init__(config_desc, config, key, self.switch_button)
        self.update_value()
        self.switch_button.toggled.connect(self.on_toggled)

    def update_value(self):
        with QSignalBlocker(self.switch_button):
            self.switch_button.setChecked(bool(self.config.get(self.key)))

    def on_toggled(self, checked):
        self.update_config(checked)


class McpServerEditor(SwitchEditor):
    """Turns the local MCP server on or off after confirming the risk."""

    def __init__(self, config_desc, config, key):
        super().__init__(config_desc, config, key)
        # An explicit CLI/config opt-in can enable MCP independently of saved settings.
        if og.ok is not None:
            with QSignalBlocker(self.switch_button):
                self.switch_button.setChecked(og.ok._mcp_server is not None)

    def on_toggled(self, checked):
        if checked:
            dialog = Dialog(self, _t('LabelAndMcpServer', 'Enable MCP Server?'), _t(
                'LabelAndMcpServer',
                'MCP lets local coding agents control this app and execute Python code '
                'with your account permissions, including reading and changing files. '
                'Only connect trusted agents and keep the connection token private. '
                'Enable the server now?'))
            accepted = dialog.exec()
            dialog.deleteLater()
            if not accepted:
                self._restore(False)
                return
        try:
            og.ok.set_mcp_enabled(checked)
            self.value_changed.emit(checked)
        except Exception as error:
            self._restore(not checked)
            dialog = Dialog(self, _t('LabelAndMcpServer', 'MCP server error'), str(error))
            dialog.set_cancel_visible(False)
            dialog.exec()
            dialog.deleteLater()

    def update_value(self):
        super().update_value()
        # A reset turns the option off; the running server must stop with it.
        if not self.config.get(self.key) and og.ok is not None and og.ok._mcp_server is not None:
            og.ok.set_mcp_enabled(False)

    def _restore(self, checked):
        with QSignalBlocker(self.switch_button):
            self.switch_button.setChecked(checked)


class NumberEditor(ConfigEditor):
    def __init__(self, config_desc, config, key, config_type=None, decimals=0):
        type_info = config_type if isinstance(config_type, dict) else {}
        default_value = config.get_default(key)
        if decimals:
            minimum = type_info.get('min', -999999999.0)
            maximum = type_info.get('max', 999999999.0)
            step = type_info.get('step', 0.1)
        else:
            if 'min' in type_info:
                minimum = type_info['min']
            elif not default_value:
                minimum = 0
            elif default_value < 0:
                minimum = -999999
            else:
                minimum = 1
            maximum = type_info.get('max', 99999999)
            step = type_info.get('step', 1)
        self.spin_box = NumberBox(config.get(key) or 0, minimum, maximum, step, decimals=decimals)
        super().__init__(config_desc, config, key, self.spin_box)
        self.spin_box.valueChanged.connect(self.update_config)

    def update_value(self):
        with QSignalBlocker(self.spin_box.spin_box):
            self.spin_box.setValue(self.config.get(self.key))


class DropDownEditor(ConfigEditor):
    def __init__(self, config_desc, options, config, key):
        self.options = list(options)
        self.combo_box = ComboBox([_app_tr(option) for option in self.options])
        super().__init__(config_desc, config, key, self.combo_box)
        self.update_value()
        self.combo_box.currentIndexChanged.connect(self._on_index_changed)

    def _on_index_changed(self, index):
        if 0 <= index < len(self.options):
            self.update_config(self.options[index])

    def update_value(self):
        value = self.config.get(self.key)
        index = self.options.index(value) if value in self.options else -1
        with QSignalBlocker(self.combo_box):
            self.combo_box.setCurrentIndex(index)


class MultiSelectionEditor(ConfigEditor):
    def __init__(self, config_desc, options, config, key):
        self.options = list(options)
        holder = QWidget()
        flow = FlowLayout(holder, spacing=10)
        self.check_boxes = []
        for option in self.options:
            box = QCheckBox(_app_tr(option))
            box.toggled.connect(self._on_toggled)
            self.check_boxes.append(box)
            flow.addWidget(box)
        super().__init__(config_desc, config, key, holder, control_width=300)
        self.update_value()

    def _on_toggled(self, _checked):
        self.update_config([option for option, box in zip(self.options, self.check_boxes) if box.isChecked()])

    def update_value(self):
        selected = self.config.get(self.key) or []
        for option, box in zip(self.options, self.check_boxes):
            with QSignalBlocker(box):
                box.setChecked(option in selected)


class LineEditEditor(ConfigEditor):
    def __init__(self, config_desc, config, key, options=None):
        from ok.ui.qt.tasks.mouse_buttons import ensure_global_filter
        self.line_edit = QLineEdit()
        # Hotkey fields accept mouse4/mouse5 through the app-wide filter.
        self.line_edit._is_hotkey_input = True
        ensure_global_filter()
        options = options if isinstance(options, dict) else {}
        width = max(CONTROL_COLUMN, options.get('minimum_width', 0))
        if options.get('maximum_width'):
            width = min(width, options['maximum_width'])
        super().__init__(config_desc, config, key, self.line_edit, control_width=width)
        self.update_value()
        self.line_edit.textChanged.connect(self.update_config)

    def update_value(self):
        with QSignalBlocker(self.line_edit):
            self.line_edit.setText(self.config.get(self.key) or "")


class TextEditEditor(ConfigEditor):
    def __init__(self, config_desc, config, key):
        self.text_edit = QPlainTextEdit()
        line = QFontMetrics(self.text_edit.font()).lineSpacing()
        self.text_edit.setFixedHeight(line * 6 + 14)
        super().__init__(config_desc, config, key, self.text_edit, control_width=340)
        self.update_value()
        self.text_edit.textChanged.connect(lambda: self.update_config(self.text_edit.toPlainText()))

    def update_value(self):
        with QSignalBlocker(self.text_edit):
            self.text_edit.setPlainText(self.config.get(self.key) or "")


class FileSelectorEditor(ConfigEditor):
    def __init__(self, config_desc, config, key, config_type=None):
        self.config_type = config_type if isinstance(config_type, dict) else {}
        self.selector_type = self.config_type.get("selector_type", "file")
        if self.selector_type not in ("file", "folder"):
            raise ValueError("file_selector selector_type must be 'file' or 'folder'")
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.value_label = Label("", "secondary")
        self.value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.browse_button = Button(_t("LabelAndFileSelector", "Browse"), "folder")
        self.browse_button.clicked.connect(self.open_selector)
        row.addWidget(self.value_label, 1)
        row.addWidget(self.browse_button)
        super().__init__(config_desc, config, key, holder, control_width=360)
        self.update_value()

    def update_value(self):
        value = str(self.config.get(self.key) or "")
        metrics = QFontMetrics(self.value_label.font())
        self.value_label.setText(metrics.elidedText(value, Qt.TextElideMode.ElideLeft, 240))
        self.value_label.setToolTip(value)

    def open_selector(self):
        current = self.config.get(self.key) or ""
        default_title = "Select Folder" if self.selector_type == "folder" else "Select File"
        title = _t("LabelAndFileSelector", self.config_type.get("dialog_title", default_title))
        start = self._initial_directory(current)
        if self.selector_type == "folder":
            path = QFileDialog.getExistingDirectory(self, title, start)
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, title, start, self.config_type.get("filter", _t("LabelAndFileSelector", "All Files (*)")))
        if path:
            self.update_config(path)
            self.update_value()

    @staticmethod
    def _initial_directory(current):
        if current:
            if os.path.isdir(current):
                return current
            directory = os.path.dirname(current)
            if directory and os.path.isdir(directory):
                return directory
        return os.getcwd()


class ButtonsEditor(ConfigEditor):
    def __init__(self, config_desc, key, buttons_config):
        if isinstance(buttons_config, dict):
            buttons_config = [buttons_config]
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addStretch(1)
        for info in buttons_config:
            icon = info.get('icon')
            button = Button(_app_tr(info.get('text', key)), nav_icon(icon) if icon else None)
            if callback := info.get('callback'):
                button.clicked.connect(callback)
            row.addWidget(button)
        super().__init__(config_desc, None, key, holder, control_width=360)


class GlobalConfigEditor(ConfigEditor):
    def __init__(self, config_desc, config, key):
        button = Button(_t("LabelAndGlobal", "Go to Config"), "chevron-right")
        super().__init__(config_desc, config, key, button)
        button.clicked.connect(self._go)

    def _go(self):
        from ok.ui.qt.Communicate import communicate
        communicate.global_config.emit(self.key)


class ListEditor(ConfigEditor):
    """Shows a list value and edits it in the list dialog."""

    def __init__(self, config_desc, config, key, options_available=None, allow_duplication=False):
        self.options_available = options_available
        self.allow_duplication = allow_duplication
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.list_label = Label("", "secondary", word_wrap=True)
        self.list_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.modify_button = Button(_t("ModifyListItem", "Modify"), "pen")
        self.modify_button.clicked.connect(self.open_dialog)
        row.addWidget(self.list_label, 1)
        row.addWidget(self.modify_button)
        super().__init__(config_desc, config, key, holder, control_width=360)
        if options_available is not None:
            items = config.get(key) or []
            valid = [item for item in items if item in options_available]
            if valid != items:
                self.config[self.key] = valid
        self.update_value()

    def update_value(self):
        items = self.config.get(self.key) or []
        if self.options_available is not None:
            items = [_app_tr(item) for item in items]
        self.list_label.setText(value_to_string(items))

    def open_dialog(self):
        from ok.ui.qt.tasks.ModifyListDialog import ModifyListDialog
        dialog = ModifyListDialog(self.config.get(self.key), self.window(), options_available=self.options_available,
                                  allow_duplication=self.allow_duplication)
        dialog.list_modified.connect(self._list_modified)
        dialog.exec()

    def _list_modified(self, items):
        if self.options_available is not None:
            items = [item for item in items if item in self.options_available]
        self.update_config(items)
        self.update_value()


def config_editor(config_type, config_desc, config, key, value, task):
    """The kit editor for ``key``; mirrors ``ConfigItemFactory.config_widget``."""

    the_type = config_type.get(key) if config_type is not None else None
    value = config.get_default(key)
    resolved = resolve_config_type(the_type, value)
    if resolved:
        if resolved == 'drop_down':
            if isinstance(value, list) and 'options_available' in the_type:
                return ListEditor(config_desc, config, key, the_type['options_available'],
                                  the_type.get('allow_duplication', False))
            return DropDownEditor(config_desc, the_type['options'], config, key)
        if resolved == 'multi_selection':
            return MultiSelectionEditor(config_desc, the_type['options'], config, key)
        if resolved == 'global':
            return GlobalConfigEditor(task.get_global_config_desc(key), task.get_global_config(key), key)
        if resolved == 'text_edit':
            return TextEditEditor(config_desc, config, key)
        if resolved == 'line_edit':
            return LineEditEditor(config_desc, config, key, the_type)
        if resolved == 'file_selector':
            if not isinstance(value, str):
                raise ValueError("file_selector config type requires a string default value")
            return FileSelectorEditor(config_desc, config, key, the_type)
        if resolved == 'button':
            return ButtonsEditor(config_desc, key, the_type.get('buttons') or [the_type])
        if resolved == 'mcp_server':
            return McpServerEditor(config_desc, config, key)
        raise ValueError(f'Unknown config type {resolved!r}')
    if isinstance(value, bool):
        return SwitchEditor(config_desc, config, key)
    if isinstance(value, list):
        options_available = the_type.get('options_available') if isinstance(the_type, dict) else None
        allow_duplication = the_type.get('allow_duplication', False) if isinstance(the_type, dict) else False
        return ListEditor(config_desc, config, key, options_available, allow_duplication)
    if isinstance(value, int):
        return NumberEditor(config_desc, config, key, the_type)
    if isinstance(value, float):
        return NumberEditor(config_desc, config, key, the_type, decimals=2)
    if isinstance(value, str):
        if value and len(value) > 16 or '\n' in value:
            return TextEditEditor(config_desc, config, key)
        return LineEditEditor(config_desc, config, key)
    raise ValueError(f"invalid type {type(value)}, value {value}")
