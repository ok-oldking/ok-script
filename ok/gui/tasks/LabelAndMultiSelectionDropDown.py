from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QFontMetrics
from PySide6.QtWidgets import QAbstractItemView
from qfluentwidgets import DropDownPushButton
from qfluentwidgets.components.widgets.combo_box import ComboBoxMenu

from ok import og
from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget


class MultiSelectComboBoxMenu(ComboBoxMenu):
    item_toggled = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view.setSelectionMode(QAbstractItemView.MultiSelection)
        self._selected_rows = set()

    def set_selected_rows(self, rows):
        self._selected_rows = set(rows)
        self.sync_selection()

    def sync_selection(self):
        for row in range(self.view.count()):
            self.view.item(row).setSelected(row in self._selected_rows)

    def _onItemClicked(self, item):
        row = self.view.row(item)
        action = item.data(0x0100)
        if row < 0 or action not in self._actions or not action.isEnabled():
            return
        self.item_toggled.emit(row)

    def exec(self, *args, **kwargs):
        self.sync_selection()
        return super().exec(*args, **kwargs)


class LabelAndMultiSelectionDropDown(ConfigLabelAndWidget):
    multi_selection_changed = Signal()

    def __init__(self, config_desc, options, config, key: str):
        super().__init__(config_desc, config, key)
        self.tr_dict = {}
        self.tr_options = []
        self.selected_rows = set()
        self.user_action = True

        for option in options:
            tr = og.app.tr(option)
            self.tr_options.append(tr)
            self.tr_dict[tr] = option

        self.menu = MultiSelectComboBoxMenu(parent=self)
        self.menu.item_toggled.connect(self.toggle_row)

        self.drop_down = DropDownPushButton(self)
        self.drop_down.setMenu(self.menu)
        self.__set_drop_down_width()

        for option in self.tr_options:
            self.menu.addAction(QAction(option, self))

        self.add_widget(self.drop_down, stretch=0)
        self.update_value()

    def __set_drop_down_width(self):
        fm = QFontMetrics(self.drop_down.font())
        max_width = 0
        for option in self.tr_options:
            max_width = max(max_width, fm.horizontalAdvance(option))
        self.drop_down.setFixedWidth(max(180, max_width + 50))

    def toggle_row(self, row):
        if row in self.selected_rows:
            self.selected_rows.remove(row)
        else:
            self.selected_rows.add(row)

        self.menu.set_selected_rows(self.selected_rows)
        self.check_changed()

    def check_changed(self):
        if not self.user_action:
            return

        options = [
            self.tr_dict.get(self.tr_options[row])
            for row in sorted(self.selected_rows)
            if 0 <= row < len(self.tr_options)
        ]
        self.update_config(options)
        self.update_button_text()
        self.multi_selection_changed.emit()

    def update_value(self):
        self.user_action = False
        selected_options = self.config.get(self.key) or []
        self.selected_rows = {
            index
            for index, option in enumerate(self.tr_options)
            if self.tr_dict[option] in selected_options
        }
        self.menu.set_selected_rows(self.selected_rows)
        self.user_action = True
        self.update_button_text()

    def update_button_text(self):
        selected = [
            self.tr_options[row]
            for row in sorted(self.selected_rows)
            if 0 <= row < len(self.tr_options)
        ]
        if not selected:
            self.drop_down.setText(og.app.tr("None"))
            return

        self.drop_down.setText(self._compact_selected_text(selected))

    def _compact_selected_text(self, selected):
        fm = QFontMetrics(self.drop_down.font())
        available_width = max(24, self.drop_down.width() - 34)
        full_text = " / ".join(selected)
        if fm.horizontalAdvance(full_text) <= available_width:
            return full_text

        if len(selected) > 2:
            summary = f"{selected[0]} / {selected[1]} / +{len(selected) - 2}"
            if fm.horizontalAdvance(summary) <= available_width:
                return summary

        if len(selected) > 1:
            summary = f"{selected[0]} / +{len(selected) - 1}"
            if fm.horizontalAdvance(summary) <= available_width:
                return summary

        return f"+{len(selected)}"
