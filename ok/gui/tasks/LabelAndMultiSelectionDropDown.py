from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QFontMetrics
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem
from qfluentwidgets import DropDownPushButton, IndicatorMenuItemDelegate, RoundMenu

from ok import og
from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget


class MultiSelectIndicatorMenuItemDelegate(IndicatorMenuItemDelegate):
    def paint(self, painter, option, index):
        action = index.data(Qt.UserRole)
        if isinstance(action, QAction) and action.isChecked():
            option = QStyleOptionViewItem(option)
            option.state |= QStyle.State_Selected
        super().paint(painter, option, index)


class MultiSelectDropDownMenu(RoundMenu):
    def _onItemClicked(self, item):
        action = item.data(Qt.UserRole)
        if action not in self._actions or not action.isEnabled():
            return
        action.trigger()


class LabelAndMultiSelectionDropDown(ConfigLabelAndWidget):
    multi_selection_changed = Signal()

    def __init__(self, config_desc, options, config, key: str):
        super().__init__(config_desc, config, key)
        self.tr_dict = {}
        self.tr_options = []
        self.user_action = True
        self.actions = []

        for option in options:
            tr = og.app.tr(option)
            self.tr_options.append(tr)
            self.tr_dict[tr] = option

        self.menu = MultiSelectDropDownMenu(parent=self)
        self.menu.view.setItemDelegate(MultiSelectIndicatorMenuItemDelegate())
        self.menu.view.setObjectName('comboListWidget')
        self.menu.setItemHeight(33)

        self.drop_down = DropDownPushButton(self)
        self.drop_down.setMenu(self.menu)
        self.__set_drop_down_width()

        for option in self.tr_options:
            action = QAction(option, self)
            action.setCheckable(True)
            action.triggered.connect(self.check_changed)
            self.actions.append(action)
            self.menu.addAction(action)

        self.add_widget(self.drop_down, stretch=0)
        self.update_value()

    def __set_drop_down_width(self):
        fm = QFontMetrics(self.drop_down.font())
        max_width = 0
        for option in self.tr_options:
            max_width = max(max_width, fm.horizontalAdvance(option))
        self.drop_down.setMinimumWidth(max(180, max_width + 50))

    def check_changed(self, *args):
        options = [
            self.tr_dict.get(action.text())
            for action in self.actions
            if action.isChecked()
        ]
        if self.user_action:
            self.update_config(options)
            self.update_button_text()
            self.multi_selection_changed.emit()

    def update_value(self):
        self.user_action = False
        selected_options = self.config.get(self.key) or []
        for action in self.actions:
            action.setChecked(self.tr_dict[action.text()] in selected_options)
        self.user_action = True
        self.update_button_text()

    def update_button_text(self):
        selected = [
            action.text()
            for action in self.actions
            if action.isChecked()
        ]
        if not selected:
            self.drop_down.setText(og.app.tr("None"))
        else:
            self.drop_down.setText(" / ".join(selected))
