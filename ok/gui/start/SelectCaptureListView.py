from PySide6.QtWidgets import QListWidgetItem
from qfluentwidgets import ListWidget

import ok.gui


class SelectCaptureListView(ListWidget):
    def __init__(self, index_change_callback):
        super().__init__()
        self.itemSelectionChanged.connect(index_change_callback)

    def update_for_device(self):
        device = ok.gui.device_manager.get_preferred_device()
        if device is not None:
            if self.count() == 0:
                item = QListWidgetItem(self.tr(f"Game Window"))
                self.addItem(item)
            selected = 0
            if device['device'] == "windows":
                title = self.tr("Game Window")
                if self.count() == 2:
                    self.takeItem(1)
            elif device.get('emulator') is not None:
                title = self.tr("ADB(Supports Background, Slow, High Compatibility, High Latency)")
                if self.count() == 1:
                    item = QListWidgetItem(self.tr("Emulator Window(Supports Background, Fast, Low Latency)"))
                    self.addItem(item)
                if ok.gui.device_manager.get_preferred_capture() == "windows":
                    selected = 1
            else:
                title = self.tr("ADB(Supports Background, Slow, High Compatibility, High Latency)")
                if self.count() == 2:
                    self.takeItem(1)
            self.item(0).setText(f"{title}")
            self.setCurrentRow(selected)
