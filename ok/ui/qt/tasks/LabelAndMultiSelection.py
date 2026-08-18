from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QPalette, QColor
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy
from qfluentwidgets import CheckBox, Theme, qconfig
from qfluentwidgets.common.style_sheet import setCustomStyleSheet

from ok import og
from ok.ui.qt.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget
from ok.ui.qt.widget.FlowLayout import FlowLayout


CHECKBOX_STYLE = (
    "QCheckBox { background: transparent; spacing: 0px; }"
    "QCheckBox::indicator { width: 18px; height: 18px; background: transparent; border-radius: 4px; }"
    "QCheckBox::indicator:unchecked { background: transparent; border-radius: 4px; }"
)


class TransparentUncheckedCheckBox(CheckBox):
    """Keep Fluent checkbox rendering while avoiding a filled unchecked box."""

    def _backgroundColor(self):
        if not self.isChecked():
            return QColor(0, 0, 0, 0)
        return super()._backgroundColor()


class WrappedCheckBox(QWidget):
    checkStateChanged = Signal(object)

    def __init__(self, text):
        super().__init__()
        self.checkbox = TransparentUncheckedCheckBox()
        self.checkbox.setFixedSize(24, 20)
        self._apply_checkbox_style()
        self.label = QLabel(text)
        self.label.setWordWrap(False)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._update_label_color()
        qconfig.themeChangedFinished.connect(self._update_label_color)
        self.checkbox.checkStateChanged.connect(self._on_state_changed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.checkbox, 0, Qt.AlignTop)
        layout.addWidget(self.label, 1, Qt.AlignVCenter)

    def _update_label_color(self, *_args):
        self._apply_checkbox_style()
        palette = self.label.palette()
        palette.setColor(
            QPalette.WindowText,
            QColor(0, 0, 0) if qconfig.theme == Theme.LIGHT else QColor(255, 255, 255),
        )
        self.label.setPalette(palette)

    def _apply_checkbox_style(self):
        setCustomStyleSheet(self.checkbox, CHECKBOX_STYLE, CHECKBOX_STYLE)

    def _on_state_changed(self, state):
        self.checkStateChanged.emit(state)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.checkbox.click()
        super().mousePressEvent(event)

    def text(self):
        return self.label.text()

    def isChecked(self):
        return self.checkbox.isChecked()

    def setChecked(self, checked):
        self.checkbox.setChecked(checked)


class LabelAndMultiSelection(ConfigLabelAndWidget):

    def __init__(self, config_desc, options, config, key: str):
        super().__init__(config_desc, config, key)
        self.key = key
        self.tr_dict = {}
        self.tr_options = []
        self.user_action = True
        for option in options:
            tr = og.app.tr(option)
            self.tr_options.append(tr)
            self.tr_dict[tr] = option
        self.content_layout = FlowLayout(alignment=Qt.AlignRight, max_columns=2)
        self.add_widget(self.content_layout, stretch=1)
        # The base row reserves a spacer before controls. Let this control
        # take that space so its single-line labels can flow into columns.
        self.layout.setStretch(1, 0)
        self.layout.setStretch(2, 1)
        self.check_boxes = []
        for option in self.tr_options:
            checkbox = WrappedCheckBox(option)
            checkbox.checkStateChanged.connect(self.check_changed)
            self.check_boxes.append(checkbox)
            self.content_layout.add_widget(checkbox)
        self.update_value()

    def check_changed(self, checked):
        options = []
        for checkbox in self.check_boxes:
            if checkbox.isChecked():
                option = self.tr_dict.get(checkbox.text())
                options.append(option)
        if self.user_action:
            self.update_config(options)

    def update_value(self):
        self.user_action = False
        for checkbox in self.check_boxes:
            checkbox.setChecked(self.tr_dict[checkbox.text()] in self.config[self.key])
        self.user_action = True


class CheckBoxWidget(QWidget):
    def __init__(self, options):
        super().__init__()

        # Create a horizontal layout
        h_layout = FlowLayout()
        h_layout = QHBoxLayout()

        # Add checkboxes to the layout
        for option in options:  # Example with 5 checkboxes
            checkbox = CheckBox(option)
            h_layout.addWidget(checkbox)
