from PySide6.QtCore import Signal
from qfluentwidgets import MessageBoxBase, SubtitleLabel, ListWidget, PushButton, FluentIcon, LineEdit


class ModifyListDialog(MessageBoxBase):
    list_modified = Signal(list)

    def __init__(self, items, parent):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr("Modify"), self)
        self.viewLayout.addWidget(self.titleLabel)
        self.original_items = items
        self.list_widget = ListWidget()
        self.list_widget.addItems(self.original_items)

        self.move_up_button = PushButton(FluentIcon.UP, self.tr("Move Up"))
        self.move_up_button.clicked.connect(self.move_up)

        self.move_down_button = PushButton(FluentIcon.DOWN, self.tr("Move Down"))
        self.move_down_button.clicked.connect(self.move_down)

        self.add_button = PushButton(FluentIcon.ADD, self.tr("Add"))
        self.add_button.clicked.connect(self.add_item)

        self.remove_button = PushButton(FluentIcon.REMOVE, self.tr("Remove"))
        self.remove_button.clicked.connect(self.remove_item)

        self.yesButton.clicked.connect(self.confirm)

        self.cancelButton.clicked.connect(self.cancel)

        self.viewLayout.addWidget(self.list_widget)
        self.viewLayout.addWidget(self.move_up_button)
        self.viewLayout.addWidget(self.move_down_button)
        self.viewLayout.addWidget(self.add_button)
        self.viewLayout.addWidget(self.remove_button)
        self.yesButton.setText(self.tr("Confirm"))
        self.cancelButton.setText(self.tr("Cancel"))

    def move_up(self):
        current_row = self.list_widget.currentRow()
        if current_row >= 1:
            item = self.list_widget.takeItem(current_row)
            self.list_widget.insertItem(current_row - 1, item)
            self.list_widget.setCurrentRow(current_row - 1)

    def move_down(self):
        current_row = self.list_widget.currentRow()
        if current_row < self.list_widget.count() - 1:
            item = self.list_widget.takeItem(current_row)
            self.list_widget.insertItem(current_row + 1, item)
            self.list_widget.setCurrentRow(current_row + 1)

    def add_item(self):
        w = AddTextMessageBox(self.window())
        if w.exec():
            self.list_widget.addItem(w.add_text_edit.text())

    def remove_item(self):
        current_row = self.list_widget.currentRow()
        if current_row >= 0:
            self.list_widget.takeItem(current_row)

    def confirm(self):
        items_text = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        self.list_modified.emit(items_text)
        self.close()

    def cancel(self):
        self.list_modified.emit(self.original_items)
        self.close()


class AddTextMessageBox(MessageBoxBase):
    """ Custom message box """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr('Add'), self)
        self.add_text_edit = LineEdit(self)

        self.add_text_edit.setClearButtonEnabled(True)

        # add widget to view layout
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.add_text_edit)

        # change the text of button
        self.yesButton.setText(self.tr('Confirm'))
        self.cancelButton.setText(self.tr('Cancel'))

        self.widget.setMinimumWidth(360)
        self.yesButton.setDisabled(True)
        self.add_text_edit.textChanged.connect(self._validate_text)

    def _validate_text(self, text):
        self.yesButton.setEnabled(True if text is not None and text.strip() else False)
