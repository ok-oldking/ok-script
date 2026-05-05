from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QSizePolicy
from PySide6.QtGui import QFont, QFontMetrics
from qfluentwidgets import PushButton, BodyLabel
from ok.gui.widget.FlowLayout import FlowLayout

from ok import og
from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget


class LabelAndButtonList(ConfigLabelAndWidget):
    """
    A widget with two-column layout:
    - Left: title and description (from ConfigLabelAndWidget)
    - Right: label (top), option buttons (middle), delete button (bottom)
    
    Usage in config_type:
        config_type = {
            'my_list': {
                'type': 'button_list',
                'options': ['Option1', 'Option2', 'Option3']
            }
        }
    """

    def __init__(self, config_desc, options, config, key: str):
        super().__init__(config_desc, config, key)
        self.options = options
        self.key = key
        
        # Create the right side vertical layout
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        
        # Top: Display label (font size: 16px, same as subtitle level)
        self.display_label = BodyLabel()
        self.display_label.setWordWrap(True)
        font = self.display_label.font()
        font.setPointSize(14)  # Match title label size (14px) with slightly larger
        self.display_label.setFont(font)
        # Limit visible lines so buttons below won't be compressed
        fm = QFontMetrics(self.display_label.font())
        max_visible_lines = 4
        max_h = fm.lineSpacing() * max_visible_lines + 6
        self.display_label.setMaximumHeight(max_h)
        self.display_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.update_display_label()
        right_layout.addWidget(self.display_label, stretch=0)
        
        # Middle: Buttons area using shared FlowLayout (wraps automatically)
        buttons_flow = FlowLayout()
        # ensure buttons area keeps reasonable height
        buttons_flow.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        buttons_flow.setMinimumHeight(40)
        self.option_buttons = []
        for option in options:
            btn = PushButton(self._translate_option(option))
            btn.clicked.connect(lambda checked=False, opt=option: self.add_item(opt))
            self.option_buttons.append(btn)
            buttons_flow.add_widget(btn)
        right_layout.addWidget(buttons_flow)
        
        # Bottom: Delete and Reset buttons
        bottom_buttons_layout = QHBoxLayout()
        bottom_buttons_layout.setContentsMargins(0, 0, 0, 0)
        bottom_buttons_layout.setSpacing(5)
        
        self.delete_btn = PushButton(og.app.tr("Delete Last Item"))
        self.delete_btn.clicked.connect(self.delete_last_item)
        self.delete_btn.setMinimumHeight(28)
        bottom_buttons_layout.addWidget(self.delete_btn)
        
        self.reset_btn = PushButton(og.app.tr("Reset"))
        self.reset_btn.clicked.connect(self.reset_to_empty)
        self.reset_btn.setMinimumHeight(28)
        bottom_buttons_layout.addWidget(self.reset_btn)
        
        bottom_buttons_layout.addStretch()
        right_layout.addLayout(bottom_buttons_layout, stretch=0)
        
        right_layout.addStretch()  # Fill remaining vertical space
        
        # Add right layout to main layout
        self.add_layout(right_layout, stretch=1)

    def add_item(self, item):
        """Add an item to the list"""
        current = self.config.get(self.key)
        if current is None:
            current = []
        # if stored as string (old), convert to list
        if isinstance(current, str):
            current = [s.strip() for s in current.split(',') if s.strip()]
        # allow duplicates
        current.append(item)
        self.update_config(current)
        self.update_display_label()

    def delete_last_item(self):
        """Delete the last item from the list"""
        current = self.config.get(self.key)
        if not current:
            return
        # normalize string fallback
        if isinstance(current, str):
            items = [item.strip() for item in current.split(',') if item.strip()]
        else:
            items = list(current)
        if items:
            items.pop()
            self.update_config(items)
            self.update_display_label()

    def reset_to_empty(self):
        """Reset the list to empty"""
        self.update_config([])
        self.update_display_label()

    def update_display_label(self):
        """Update the display label text"""
        value = self.config.get(self.key)
        if value is None:
            display = ""
        elif isinstance(value, list):
            display = ", ".join(self._translate_option(item) for item in value)
        else:
            # fallback for old string-based storage
            display = self._translate_option(str(value))
        self.display_label.setText(display if display else og.app.tr("(empty)"))

    def update_value(self):
        """Update the display when config changes externally"""
        self.update_display_label()

    def _translate_option(self, option):
        translated = og.app.tr(str(option))
        return translated if translated else str(option)
