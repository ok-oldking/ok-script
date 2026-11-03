from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QListWidget, QScrollArea, QVBoxLayout, QWidget

from ok import og
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.dialogs import Dialog
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.layout import FlowLayout
from ok.ui.qt.util.touch_scroll import enable_touch_scrolling

SHOW_SEARCH_OPTIONS_THRESHOLD = 20


class ModifyListDialog(Dialog):
    """Edit an ordered list of strings, free-form or picked from ``options_available``.

    ``list_modified`` carries the new list on Confirm and the original list on Cancel.
    """

    list_modified = Signal(list)

    def __init__(self, items, parent, options_available=None, allow_duplication=False):
        picking = options_available is not None
        super().__init__(parent, "", width=860 if picking else 520)
        self.title_label.setText(self.tr("Edit List"))
        self.ok_button.setText(self.tr("Confirm"))
        self.original_items = list(items)
        self.options_available = list(options_available) if picking else None
        self.allow_duplication = allow_duplication
        self.option_buttons = {}
        self.source_by_display = {}
        self.option_search_box = None
        self._options_container = None
        panel = self.panel

        self.list_widget = QListWidget(panel)
        self.list_widget.setObjectName("featureList")
        self.list_widget.setMinimumHeight(320)
        if picking:
            self.source_by_display = {og.app.tr(option): option for option in self.options_available}
            self.list_widget.addItems([og.app.tr(item) for item in self.original_items
                                       if item in self.options_available])
        else:
            self.list_widget.addItems(self.original_items)

        self.move_up_button = Button(self.tr("Move Up"), "chevron-up", parent=panel)
        self.move_up_button.clicked.connect(self.move_up)
        self.move_down_button = Button(self.tr("Move Down"), "chevron-down", parent=panel)
        self.move_down_button.clicked.connect(self.move_down)
        self.add_button = None
        if not picking:
            self.add_button = Button(self.tr("Add"), "plus", parent=panel)
            self.add_button.clicked.connect(self.add_item)
        self.remove_button = Button(self.tr("Remove"), "trash", "subtle", parent=panel)
        self.remove_button.clicked.connect(self.remove_item)
        self.list_widget.itemSelectionChanged.connect(self.update_list_actions)
        self.accepted.connect(self.confirm)
        self.rejected.connect(self.cancel)

        list_layout = self._create_selected_list_layout()
        if not picking:
            self.body.addLayout(list_layout)
        else:
            available_layout = QVBoxLayout()
            available_layout.setSpacing(8)
            available_layout.addWidget(Label(self.tr("Available Options"), "strong", panel))
            available_layout.addWidget(Label(self.tr("Click an option to add it."), "caption", panel))
            if len(self.options_available) > SHOW_SEARCH_OPTIONS_THRESHOLD:
                self.option_search_box = QLineEdit(panel)
                self.option_search_box.setClearButtonEnabled(True)
                self.option_search_box.setPlaceholderText(self.tr("Search options..."))
                self.option_search_box.textChanged.connect(self.filter_available_options)
                available_layout.addWidget(self.option_search_box)
            scroll = QScrollArea(panel)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setMinimumHeight(360)
            self._options_container = self._create_available_options_widget()
            scroll.setWidget(self._options_container)
            enable_touch_scrolling(scroll)
            available_layout.addWidget(scroll, 1)

            selected_layout = QVBoxLayout()
            selected_layout.setSpacing(8)
            selected_layout.addWidget(Label(self.tr("Selected Options"), "strong", panel))
            selected_layout.addLayout(list_layout)

            options_layout = QHBoxLayout()
            options_layout.setSpacing(20)
            options_layout.addLayout(available_layout, 2)
            options_layout.addLayout(selected_layout, 1)
            self.body.addLayout(options_layout)

        self.update_list_actions()

    def _create_selected_list_layout(self):
        actions_layout = QVBoxLayout()
        actions_layout.setSpacing(6)
        for button in (self.move_up_button, self.move_down_button, self.add_button, self.remove_button):
            if button is not None:
                actions_layout.addWidget(button)
        actions_layout.addStretch(1)
        list_layout = QHBoxLayout()
        list_layout.setSpacing(10)
        list_layout.addWidget(self.list_widget, 1)
        list_layout.addLayout(actions_layout)
        return list_layout

    def _create_available_options_widget(self):
        widget = QWidget()
        widget.setObjectName("scrollContents")
        layout = FlowLayout(widget, spacing=8)
        for option in self.options_available:
            button = Button(og.app.tr(option), "plus", size="small", parent=widget)
            button.clicked.connect(lambda checked=False, value=option: self.add_available_item(value))
            layout.addWidget(button)
            self.option_buttons[option] = button
        return widget

    def update_list_actions(self):
        row = self.list_widget.currentRow()
        has_selection = row >= 0
        self.move_up_button.setEnabled(has_selection and row > 0)
        self.move_down_button.setEnabled(has_selection and row < self.list_widget.count() - 1)
        self.remove_button.setEnabled(has_selection)
        self.update_option_buttons()

    def update_option_buttons(self):
        if self.options_available is None:
            return
        selected = {self.list_widget.item(i).text() for i in range(self.list_widget.count())}
        for option, button in self.option_buttons.items():
            button.setEnabled(self.allow_duplication or og.app.tr(option) not in selected)

    def filter_available_options(self, text):
        keyword = text.strip().casefold()
        for option, button in self.option_buttons.items():
            display_text = og.app.tr(option)
            button.setVisible(not keyword or keyword in option.casefold() or keyword in display_text.casefold())
        if self._options_container is not None and self._options_container.layout() is not None:
            self._options_container.layout().invalidate()

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
        dialog = AddTextMessageBox(self)
        try:
            if dialog.exec():
                self.list_widget.addItem(dialog.add_text_edit.text())
                self.list_widget.setCurrentRow(self.list_widget.count() - 1)
        finally:
            dialog.deleteLater()

    def add_available_item(self, option):
        text = og.app.tr(option)
        if self.allow_duplication or all(
                self.list_widget.item(i).text() != text for i in range(self.list_widget.count())):
            self.list_widget.addItem(text)
            self.list_widget.setCurrentRow(self.list_widget.count() - 1)
            self.update_option_buttons()

    def remove_item(self):
        current_row = self.list_widget.currentRow()
        if current_row >= 0:
            self.list_widget.takeItem(current_row)
            self.update_list_actions()

    def items(self):
        items_text = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        if self.options_available is not None:
            items_text = [self.source_by_display[text] for text in items_text]
        return items_text

    def confirm(self):
        self.list_modified.emit(self.items())

    def cancel(self):
        self.list_modified.emit(self.original_items)


class AddTextMessageBox(Dialog):
    """Ask for one non-empty line of text."""

    def __init__(self, parent=None):
        super().__init__(parent, "", width=400)
        self.title_label.setText(self.tr('Add'))
        self.add_text_edit = QLineEdit(self.panel)
        self.add_text_edit.setClearButtonEnabled(True)
        self.body.addWidget(self.add_text_edit)
        self.ok_button.setEnabled(False)
        self.add_text_edit.textChanged.connect(lambda text: self.ok_button.setEnabled(bool(text and text.strip())))

    def open(self):
        super().open()
        self.add_text_edit.setFocus()
