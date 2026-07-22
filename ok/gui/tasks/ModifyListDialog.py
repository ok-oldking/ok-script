from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QHBoxLayout, QScroller, QScrollArea, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, FlowLayout, MessageBoxBase, SubtitleLabel, ListWidget, PushButton, FluentIcon,
    LineEdit
)

from ok import og


SHOW_SEARCH_OPTIONS_THRESHOLD = 20


class ModifyListDialog(MessageBoxBase):
    list_modified = Signal(list)

    def __init__(self, items, parent, options_available=None, allow_duplication=False):
        super().__init__(parent)
        self.original_items = list(items)
        self.options_available = list(options_available) if options_available is not None else None
        self.allow_duplication = allow_duplication
        self.list_widget = ListWidget()
        self.option_buttons = {}
        self.source_by_display = {}
        self.option_search_box = None
        self._options_container = None

        if self.options_available is None:
            self.list_widget.addItems(self.original_items)
        else:
            self.source_by_display = {
                og.app.tr(option): option for option in self.options_available
            }
            self.list_widget.addItems([
                og.app.tr(item) for item in self.original_items if item in self.options_available
            ])

        self.move_up_button = PushButton(FluentIcon.UP, self.tr("Move Up"))
        self.move_up_button.clicked.connect(self.move_up)

        self.move_down_button = PushButton(FluentIcon.DOWN, self.tr("Move Down"))
        self.move_down_button.clicked.connect(self.move_down)

        self.add_button = None
        if self.options_available is None:
            self.add_button = PushButton(FluentIcon.ADD, self.tr("Add"))
            self.add_button.clicked.connect(self.add_item)

        self.remove_button = PushButton(FluentIcon.REMOVE, self.tr("Remove"))
        self.remove_button.clicked.connect(self.remove_item)
        self.list_widget.itemSelectionChanged.connect(self.update_list_actions)
        self._match_list_action_widths()

        self.yesButton.clicked.connect(self.confirm)

        self.cancelButton.clicked.connect(self.cancel)

        list_layout = self._create_selected_list_layout()

        if self.options_available is None:
            self.viewLayout.addLayout(list_layout)
        else:
            available_layout = QVBoxLayout()
            available_layout.addWidget(SubtitleLabel(self.tr("Available Options"), self))
            available_layout.addWidget(BodyLabel(self.tr("Click an option to add it."), self))
            if len(self.options_available) > SHOW_SEARCH_OPTIONS_THRESHOLD:
                self.option_search_box = LineEdit(self)
                self.option_search_box.setClearButtonEnabled(True)
                self.option_search_box.setPlaceholderText(self.tr("Search options..."))
                self.option_search_box.textChanged.connect(self.filter_available_options)
                available_layout.addWidget(self.option_search_box)
            available_scroll_area = QScrollArea(self)
            available_scroll_area.setWidgetResizable(True)
            available_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            available_scroll_area.setFrameShape(QScrollArea.NoFrame)
            available_scroll_area.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
            available_scroll_area.viewport().setStyleSheet("background-color: transparent;")
            QScroller.grabGesture(
                available_scroll_area.viewport(),
                QScroller.ScrollerGestureType.TouchGesture,
            )
            self._options_container = self._create_available_options_widget()
            available_scroll_area.setWidget(self._options_container)
            available_layout.addWidget(available_scroll_area, stretch=1)

            selected_layout = QVBoxLayout()
            selected_layout.addWidget(SubtitleLabel(self.tr("Selected Options"), self))
            selected_layout.addLayout(list_layout)

            options_layout = QHBoxLayout()
            options_layout.addLayout(available_layout, stretch=2)
            options_layout.addLayout(selected_layout, stretch=1)
            self.viewLayout.addLayout(options_layout)

        self.yesButton.setText(self.tr("Confirm"))
        self.cancelButton.setText(self.tr("Cancel"))
        self._wrap_dialog_buttons()
        if self.options_available is None:
            self.widget.setMinimumHeight(520)
        else:
            self.widget.setMinimumSize(840, 600)
        self.update_list_actions()
        self.update_option_buttons()

    def _create_selected_list_layout(self):
        actions_layout = QVBoxLayout()
        actions_layout.addWidget(self.move_up_button)
        actions_layout.addWidget(self.move_down_button)
        if self.options_available is None:
            actions_layout.addWidget(self.add_button)
        actions_layout.addWidget(self.remove_button)
        actions_layout.addStretch(1)

        list_layout = QHBoxLayout()
        list_layout.addWidget(self.list_widget)
        list_layout.addLayout(actions_layout)
        return list_layout

    def _create_available_options_widget(self):
        widget = QWidget()
        widget.setStyleSheet("background-color: transparent;")
        layout = FlowLayout(widget, False, isTight=True)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)
        for option in self.options_available:
            button = PushButton(FluentIcon.ADD, og.app.tr(option))
            button.clicked.connect(lambda checked=False, value=option: self.add_available_item(value))
            layout.addWidget(button)
            self.option_buttons[option] = button
        return widget

    def _match_list_action_widths(self):
        buttons = [self.move_up_button, self.move_down_button, self.remove_button]
        if self.options_available is None:
            buttons.append(self.add_button)
        width = max(button.sizeHint().width() for button in buttons)
        for button in buttons:
            button.setFixedWidth(width)

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

        selected_options = {
            self.list_widget.item(i).text() for i in range(self.list_widget.count())
        }
        for option, button in self.option_buttons.items():
            button.setEnabled(self.allow_duplication or og.app.tr(option) not in selected_options)

    def filter_available_options(self, text):
        keyword = text.strip().casefold()
        for option, button in self.option_buttons.items():
            display_text = og.app.tr(option)
            button.setVisible(
                not keyword
                or keyword in option.casefold()
                or keyword in display_text.casefold()
            )
        # Force the FlowLayout to recalculate and skip hidden widgets (isTight=True)
        if self._options_container is not None:
            layout = self._options_container.layout()
            if layout is not None:
                layout.setGeometry(self._options_container.geometry())
                self._options_container.update()

    def _wrap_dialog_buttons(self):
        self.yesButton.setFixedWidth(self.yesButton.sizeHint().width() * 2)
        self.cancelButton.setFixedWidth(self.cancelButton.sizeHint().width() * 2)

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
            self.list_widget.setCurrentRow(self.list_widget.count() - 1)

    def add_available_item(self, option):
        text = og.app.tr(option)
        if self.allow_duplication or all(
            self.list_widget.item(i).text() != text for i in range(self.list_widget.count())
        ):
            self.list_widget.addItem(text)
            self.list_widget.setCurrentRow(self.list_widget.count() - 1)
            self.update_option_buttons()

    def remove_item(self):
        current_row = self.list_widget.currentRow()
        if current_row >= 0:
            self.list_widget.takeItem(current_row)
            self.update_list_actions()

    def confirm(self):
        items_text = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        if self.options_available is not None:
            items_text = [self.source_by_display[text] for text in items_text]
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
        self.yesButton.setFixedWidth(self.yesButton.sizeHint().width() * 2)
        self.cancelButton.setFixedWidth(self.cancelButton.sizeHint().width() * 2)

        self.widget.setMinimumWidth(360)
        self.yesButton.setDisabled(True)
        self.add_text_edit.textChanged.connect(self._validate_text)

    def _validate_text(self, text):
        self.yesButton.setEnabled(True if text is not None and text.strip() else False)
