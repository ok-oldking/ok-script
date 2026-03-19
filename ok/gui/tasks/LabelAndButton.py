from qfluentwidgets import PushButton
from ok.gui.tasks.LabelAndWidget import LabelAndWidget
from ok import og


class LabelAndButton(LabelAndWidget):
    def __init__(self, config_desc, key: str, text: str, icon, callback):
        desc = None
        if config_desc is not None:
            desc = config_desc.get(key)
        super().__init__(key, desc)

        # Translate the button text
        translated_text = og.app.tr(text)

        if icon:
            self.button = PushButton(icon, translated_text)
        else:
            self.button = PushButton(translated_text)

        if callback:
            self.button.clicked.connect(callback)

        self.add_widget(self.button)

    def update_value(self):
        pass
