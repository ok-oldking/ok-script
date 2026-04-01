from PySide6.QtWidgets import QListWidgetItem
from qfluentwidgets import ListWidget
from ok import og

class SelectInteractionListView(ListWidget):
    def __init__(self, index_change_callback):
        super().__init__()
        self.itemSecondChangedCallback = index_change_callback
        self.itemSelectionChanged.connect(self.itemSecondChangedCallback)

    def update_for_device(self):
        device = og.device_manager.get_preferred_device()
        if device is not None:
            self.blockSignals(True)
            if self.count() == 0:
                item = QListWidgetItem(self.tr("Default Interaction"))
                self.addItem(item)
            selected = 0
            if device['device'] == "windows":
                methods = og.device_manager.windows_capture_config.get('interaction', [])
                if isinstance(methods, str):
                    methods = [methods]
                if not methods:
                    title = self.tr("WindowsInteraction")
                    self.reduce_row_to_1()
                    self.item(0).setText(f"{title}")
                    selected = 0
                else:
                    while self.count() > len(methods):
                        self.takeItem(self.count() - 1)
                    for i, method in enumerate(methods):
                        if i < self.count():
                            self.item(i).setText(self.tr(method))
                        else:
                            self.addItem(QListWidgetItem(self.tr(method)))
                    current_interaction = og.device_manager.config.get("interaction")
                    if current_interaction in methods:
                        selected = methods.index(current_interaction)
            elif device['device'] == "adb":
                title = self.tr("ADBInteraction")
                self.reduce_row_to_1()
                self.item(0).setText(f"{title}")
                selected = 0
            elif device['device'] == "browser":
                title = self.tr("BrowserInteraction")
                self.reduce_row_to_1()
                self.item(0).setText(f"{title}")
                selected = 0
            else:
                title = self.tr("Default Interaction")
                self.reduce_row_to_1()
                self.item(0).setText(f"{title}")
                selected = 0
            self.blockSignals(False)
            self.setCurrentRow(selected)

    def reduce_row_to_1(self):
        while self.count() > 1:
            self.takeItem(self.count() - 1)
