import os

from PySide6.QtWidgets import QFileDialog, QHBoxLayout
from qfluentwidgets import FluentIcon, PushButton

from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget


class LabelAndFileSelector(ConfigLabelAndWidget):
    MIN_VALUE_WIDTH = 280

    def __init__(self, config_desc, config, key: str, config_type=None):
        super().__init__(config_desc, config, key)
        self.key = key
        self.config_type = config_type if isinstance(config_type, dict) else {}
        self.selector_type = self.config_type.get("selector_type", "file")
        if self.selector_type not in ("file", "folder"):
            raise ValueError("file_selector selector_type must be 'file' or 'folder'")

        self.value_label = self._create_value_label()
        self.browse_button = PushButton(FluentIcon.FOLDER, self.tr("Browse"))
        self.browse_button.clicked.connect(self.open_selector)

        layout = QHBoxLayout()
        layout.addWidget(self.value_label)
        layout.addWidget(self.browse_button)
        self.add_layout(layout, stretch=0)

        self.update_value()

    def update_value(self):
        value = self.config.get(self.key) or ""
        self.value_label.setText(str(value))

    def open_selector(self):
        if self.selector_type == "folder":
            self.open_folder_selector()
        else:
            self.open_file_selector()

    def open_file_selector(self):
        current_value = self.config.get(self.key) or ""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self._dialog_title(),
            self._initial_directory(current_value),
            self.config_type.get("filter", self.tr("All Files (*)")),
        )
        if file_path:
            self.update_config(file_path)
            self.update_value()

    def open_folder_selector(self):
        current_value = self.config.get(self.key) or ""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            self._dialog_title(),
            self._initial_directory(current_value),
        )
        if folder_path:
            self.update_config(folder_path)
            self.update_value()

    def _dialog_title(self):
        default_title = "Select Folder" if self.selector_type == "folder" else "Select File"
        return self.tr(self.config_type.get("dialog_title", default_title))

    def _create_value_label(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QLabel

        label = QLabel()
        label.setMinimumWidth(self.MIN_VALUE_WIDTH)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        font = label.font()
        if font.pointSize() > 0:
            font.setPointSize(font.pointSize() + 1)
            label.setFont(font)
        return label

    def _initial_directory(self, current_value):
        if current_value:
            if os.path.isdir(current_value):
                return current_value
            directory = os.path.dirname(current_value)
            if directory and os.path.isdir(directory):
                return directory
        return os.getcwd()
