from PySide6.QtWidgets import QListWidgetItem, QListWidget

import ok


class SelectCaptureListView(QListWidget):
    def __init__(self, index_change_callback):
        super().__init__()

        self.itemSelectionChanged.connect(index_change_callback)

    def update_for_device(self, device, hwnd):
        item = QListWidgetItem(self.tr(f"Game Window(Supports Background, Low Compatibility, Low Latency)"))

        # Add the QListWidgetItem to the QListWidget
        self.addItem(item)
        tips = self.tr("Supports Background, Low Compatibility, Low Latency")
        if device == "windows":
            title = self.tr("Game Window")
            if self.count() == 2:
                self.takeItem(1)
        else:
            title = self.tr("Emulator Window")
            if self.count() == 1:
                item = QListWidgetItem(self.tr("ADB (Supports Background, High Compatibility, High Latency)"))
                self.addItem(item)
        if name := ok.gui.device_manager.get_hwnd_name():
            tips = name
        self.item(0).setText(f"{title}({tips})")
        if self.currentRow() == -1:
            self.setCurrentRow(self.count() - 1)
