from PySide6.QtWidgets import QComboBox

from ok.gui.widget.UpdateConfigWidgetItem import UpdateConfigWidgetItem


class YesNonWidgetItem(UpdateConfigWidgetItem, QComboBox):

    def __init__(self, config, key, value):
        UpdateConfigWidgetItem.__init__(self, config, key, value)
        QComboBox.__init__(self)
        self.addItems(["Yes", "No"])
        if value:
            self.setCurrentIndex(0)
        else:
            self.setCurrentIndex(1)

        self.currentIndexChanged.connect(self.index_changed)

    def index_changed(self, index):
        if index == 0:
            self.set_value(True)
        else:
            self.set_value(False)
