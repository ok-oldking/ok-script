from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QSizePolicy, QWidget
from PySide6.QtGui import QFontMetrics
from qfluentwidgets import PushButton, BodyLabel, FlowLayout

from ok import og
from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget
class LabelAndButtonList(ConfigLabelAndWidget):
    def __init__(self, config_desc, options, config, key: str):
        super().__init__(config_desc, config, key)
        self.options = options
        self.key = key

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        self.display_label = BodyLabel()
        self.display_label.setWordWrap(True)
        font = self.display_label.font()
        font.setPointSize(14)
        self.display_label.setFont(font)

        fm = QFontMetrics(self.display_label.font())
        self.display_label.setMaximumHeight(fm.lineSpacing() * 4 + 6)
        self.display_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.update_display_label()
        right_layout.addWidget(self.display_label, stretch=0)

        buttons_container = QWidget()
        buttons_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        buttons_flow = FlowLayout(buttons_container, False)
        buttons_flow.setContentsMargins(0, 0, 0, 0)
        buttons_flow.setVerticalSpacing(8)
        buttons_flow.setHorizontalSpacing(8)
        buttons_container.setMinimumHeight(40)
        self.option_buttons = []
        for option in options:
            button = PushButton(self._translate_option(option))
            button.clicked.connect(lambda checked=False, opt=option: self.add_item(opt))
            self.option_buttons.append(button)
            buttons_flow.addWidget(button)
        right_layout.addWidget(buttons_container)

        bottom_buttons_layout = QHBoxLayout()
        bottom_buttons_layout.setContentsMargins(0, 0, 0, 0)
        bottom_buttons_layout.setSpacing(5)

        self.delete_btn = PushButton(self.tr("Delete Last Item"))
        self.delete_btn.clicked.connect(self.delete_last_item)
        self.delete_btn.setMinimumHeight(28)
        bottom_buttons_layout.addWidget(self.delete_btn)

        self.reset_btn = PushButton(self.tr("Reset"))
        self.reset_btn.clicked.connect(self.reset_to_empty)
        self.reset_btn.setMinimumHeight(28)
        bottom_buttons_layout.addWidget(self.reset_btn)

        bottom_buttons_layout.addStretch()
        right_layout.addLayout(bottom_buttons_layout, stretch=0)
        right_layout.addStretch()

        self.add_layout(right_layout, stretch=1)

    def add_item(self, item):
        current = self.config.get(self.key)
        # only accept list values; if not a list, initialize to empty list
        if not isinstance(current, list):
            current = []

        current.append(item)
        self.update_config(current)
        self.update_display_label()

    def delete_last_item(self):
        current = self.config.get(self.key)
        # only operate on lists
        if not isinstance(current, list) or not current:
            return

        items = list(current)
        items.pop()
        self.update_config(items)
        self.update_display_label()

    def reset_to_empty(self):
        self.update_config([])
        self.update_display_label()

    def update_display_label(self):
        value = self.config.get(self.key)
        # only list values are considered; otherwise display empty
        if isinstance(value, list):
            display = ", ".join(self._translate_option(item) for item in value)
        else:
            display = ""

        self.display_label.setText(display if display else self.tr("(empty)"))

    def update_value(self):
        self.update_display_label()

    def _translate_option(self, option):
        translated = og.app.tr(str(option))
        return translated if translated else str(option)