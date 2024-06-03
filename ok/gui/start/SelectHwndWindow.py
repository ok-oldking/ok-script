import win32gui
from qfluentwidgets import MessageBoxBase, ListWidget, LineEdit, SubtitleLabel

import ok
from ok.capture.HwndWindow import enum_windows


# Function to get all windows


class SelectHwndWindow(MessageBoxBase):
    def __init__(self, emulator_path, callback, parent):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr("Select Window"), self)
        self.callback = callback
        self.viewLayout.addWidget(self.titleLabel)

        self.filter_edit = LineEdit()
        self.filter_edit.setPlaceholderText("Filter by name")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self.update_list)
        self.viewLayout.addWidget(self.filter_edit)

        self.list_widget = ListWidget()
        self.viewLayout.addWidget(self.list_widget)
        self.list_widget.currentRowChanged.connect(self.row_selected)  # Connect the signal to the slot

        self.yesButton.setText(self.tr('Confirm'))
        self.yesButton.setEnabled(False)
        self.accepted.connect(self.confirm)
        self.cancelButton.setText(self.tr('Cancel'))

        self.hwnds = enum_windows(emulator_path)
        self.filtered_hwnds = []  # Add this line
        self.update_list()

    def update_list(self):
        self.list_widget.clear()
        self.filtered_hwnds = []  # Clear the filtered list
        filter_text = self.filter_edit.text().lower()
        for hwnd, title, width, height in self.hwnds:
            if filter_text in title.lower():
                self.list_widget.addItem(f"{title} ({width}x{height})")
                self.filtered_hwnds.append((hwnd, title, width, height))  # Add to the filtered list

    def confirm(self):
        i = self.list_widget.currentRow()
        if i >= 0:
            title = self.filtered_hwnds[i][1]  # Use the filtered list
            ok.gui.device_manager.set_hwnd_name(title)
            self.callback()

    def row_selected(self, row):
        # Enable the button if a row is selected, disable it otherwise
        self.yesButton.setEnabled(row != -1)
