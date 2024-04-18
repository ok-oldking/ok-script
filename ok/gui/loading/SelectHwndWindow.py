import win32gui
from PySide6.QtWidgets import QVBoxLayout, QPushButton, QListWidget, QLineEdit, QDialog

import ok


# Function to get all windows
def enum_windows():
    def callback(hwnd, extra):
        buff = win32gui.GetWindowText(hwnd)
        if buff and win32gui.IsWindowVisible(hwnd):
            rect = win32gui.GetWindowRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            extra.append((hwnd, buff, width, height))
        return True

    windows = []
    win32gui.EnumWindows(callback, windows)
    return windows


class SelectHwndWindow(QDialog):
    def __init__(self, callback):
        super().__init__()
        self.setWindowTitle(self.tr("Select Window"))
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.setModal(True)
        self.callback = callback
        self.setWindowIcon(ok.gui.app.icon)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by name")
        self.filter_edit.textChanged.connect(self.update_list)
        self.layout.addWidget(self.filter_edit)

        self.list_widget = QListWidget()
        self.layout.addWidget(self.list_widget)
        self.list_widget.currentRowChanged.connect(self.row_selected)  # Connect the signal to the slot

        self.confirm_button = QPushButton("Confirm")
        self.confirm_button.clicked.connect(self.confirm)
        self.confirm_button.setEnabled(False)  # Disable the button initially
        self.layout.addWidget(self.confirm_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.close)
        self.layout.addWidget(self.cancel_button)
        self.hwnds = enum_windows()
        self.update_list()

    def update_list(self):
        self.list_widget.clear()
        filter_text = self.filter_edit.text().lower()
        for hwnd, title, width, height in self.hwnds:
            if filter_text in title.lower():
                self.list_widget.addItem(f"{title} ({width}x{height})")

    def confirm(self):
        i = self.list_widget.currentRow()
        if i >= 0:
            title = self.hwnds[i][1]
            ok.gui.device_manager.set_hwnd_name(title)
            self.callback()
            self.close()

    def row_selected(self, row):
        # Enable the button if a row is selected, disable it otherwise
        self.confirm_button.setEnabled(row != -1)
