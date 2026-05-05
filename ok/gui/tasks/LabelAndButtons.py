from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import PushButton

from ok import og
from ok.gui.tasks.LabelAndWidget import LabelAndWidget


class LabelAndButtons(LabelAndWidget):
    def __init__(self, config_desc, key: str, buttons_config):
        desc = None
        if config_desc is not None:
            desc = config_desc.get(key)
        super().__init__(key, desc)

        # QHBoxLayout for buttons, will be added to the right of the label
        button_layout = QHBoxLayout()

        if isinstance(buttons_config, dict):
            # Single button config compatible with previous version
            buttons_config = [buttons_config]

        for btn_info in buttons_config:
            text = btn_info.get('text', key)
            icon = btn_info.get('icon')
            callback = btn_info.get('callback')

            # Translate the button text
            translated_text = og.app.tr(text)

            if icon:
                btn = PushButton(icon, translated_text)
            else:
                btn = PushButton(translated_text)

            if callback:
                btn.clicked.connect(callback)

            button_layout.addWidget(btn)

        self.add_layout(button_layout, stretch=0)

    def update_value(self):
        pass
