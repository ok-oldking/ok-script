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
            self.blockSignals(True)
            if self.count() == 0:
                item = QListWidgetItem(self.tr(f"Game Window"))
                self.addItem(item)
            selected = 0
            if device['device'] == "windows":
                methods = og.device_manager.windows_capture_config.get('capture_method', [])
                if not methods:
                    title = self.tr("Game Window")
                    self.reduce_row_to_1()
                    self.item(0).setText(f"{title}")
                    selected = 0
                else:
                    while self.count() > len(methods):
                        self.takeItem(self.count() - 1)
                    for i, method in enumerate(methods):
                        method_name = method.__name__ if isinstance(method, type) else str(method)
                        if i < self.count():
                            self.item(i).setText(self.tr(method_name))
                        else:
                            self.addItem(QListWidgetItem(self.tr(method_name)))
                    current_capture = og.device_manager.get_preferred_capture()
                    for i, method in enumerate(methods):
                        method_name = method.__name__ if isinstance(method, type) else str(method)
                        if current_capture == method_name:
                            selected = i
                            break
            elif device.get('device') == "browser":
                title = self.tr("Browser Capture")
                self.reduce_row_to_1()
                self.item(0).setText(f"{title}")
                selected = 0
            elif device.get('emulator') is not None:
                title = self.tr("ADB(Supports Background, Slow, High Compatibility, High Latency)")
                self.reduce_row_to_1()
                self.item(0).setText(f"{title}")
                from ok.alas.emulator_windows import Emulator
                if device.get('emulator') and device.get(
                        'emulator').type == Emulator.MuMuPlayer12 and "MuMuPlayerGlobal" not in device.get(
                    'emulator').path:
                    item = QListWidgetItem(self.tr("Ipc (MuMuPlayer12 version >= 4.0)"))
                    self.addItem(item)
                    if og.device_manager.config.get('capture') == 'adb':
                        selected = 0
                    else:
                        selected = 1
                else:
                    selected = 0
            else:
                title = self.tr("ADB(Supports Background, Slow, High Compatibility, High Latency)")
                self.reduce_row_to_1()
                self.item(0).setText(f"{title}")
                selected = 0
            
            self.blockSignals(False)
            self.setCurrentRow(selected)

    def reduce_row_to_1(self):
        while self.count() > 1:
            self.takeItem(self.count() - 1)
