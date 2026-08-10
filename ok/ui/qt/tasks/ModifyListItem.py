from qfluentwidgets import PushButton, BodyLabel

from ok import og
from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget
from ok.gui.tasks.ModifyListDialog import ModifyListDialog
from ok.gui.widget.UpdateConfigWidgetItem import value_to_string


class ModifyListItem(ConfigLabelAndWidget):

    def __init__(self, config_desc, config, key: str, options_available=None, allow_duplication=False):
        super().__init__(config_desc, config, key)
        self.options_available = options_available
        self.allow_duplication = allow_duplication
        if self.options_available is not None:
            self._restrict_to_available_options()
        self.switch_button = PushButton(self.tr('Modify'))
        self.switch_button.clicked.connect(self.clicked)
        self.list_text = BodyLabel("")
        self.update_value()
        self.add_widget(self.list_text, stretch=0)
        self.add_widget(self.switch_button, stretch=0)

    def update_value(self):
        items = self.config.get(self.key)
        if self.options_available is not None:
            items = [og.app.tr(item) for item in items]
        total_length = sum(len(item) for item in items)

        if total_length > 30:
            display_text = "\n".join(items)
        else:
            display_text = value_to_string(items)

        self.list_text.setText(display_text)

    def clicked(self):
        dialog = ModifyListDialog(
            self.config.get(self.key), self.window(), options_available=self.options_available,
            allow_duplication=self.allow_duplication
        )
        dialog.list_modified.connect(self.list_modified)
        dialog.exec()

    def list_modified(self, the_list):
        if self.options_available is not None:
            the_list = [item for item in the_list if item in self.options_available]
        self.update_config(the_list)
        self.update_value()

    def _restrict_to_available_options(self):
        items = self.config.get(self.key)
        valid_items = [item for item in items if item in self.options_available]
        if valid_items != items:
            self.update_config(valid_items)
