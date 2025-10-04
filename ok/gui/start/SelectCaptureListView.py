from PySide6.QtWidgets import QListWidgetItem
from qfluentwidgets import ListWidget

from ok import og


class SelectCaptureListView(ListWidget):
    def __init__(self, index_change_callback):
        super().__init__()
        self.itemSelectionChanged.connect(index_change_callback)

    def update_for_device(self):
        device = og.device_manager.get_preferred_device()
        if device is not None:
            if self.count() == 0:
                item = QListWidgetItem(self.tr(f"Game Window"))
                self.addItem(item)
            selected = 0
            if device['device'] == "windows":
                title = self.tr("Game Window")
                self.reduce_row_to_1()
            elif device.get('emulator') is not None:
                title = self.tr("ADB(Supports Background, Slow, High Compatibility, High Latency)")
                from ok.alas.emulator_windows import Emulator
                if device.get('emulator') and device.get(
                        'emulator').type == Emulator.MuMuPlayer12 and "MuMuPlayerGlobal" not in device.get(
                    'emulator').path:
                    if self.count() == 1:
                        item = QListWidgetItem(self.tr("Ipc (MuMuPlayer12 version >= 4.0)"))
                        self.addItem(item)
                    selected = 1
                else:
                    self.reduce_row_to_1()
                    selected = 0
            else:
                title = self.tr("ADB(Supports Background, Slow, High Compatibility, High Latency)")
                self.reduce_row_to_1()
            self.item(0).setText(f"{title}")
            self.setCurrentRow(selected)

    def reduce_row_to_1(self):
        while self.count() > 1:
            self.takeItem(self.count() - 1)
