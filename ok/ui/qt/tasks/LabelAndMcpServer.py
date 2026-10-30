from PySide6.QtCore import QSignalBlocker
from qfluentwidgets import MessageBox

from ok import og
from ok.ui.qt.tasks.LabelAndSwitchButton import LabelAndSwitchButton


class LabelAndMcpServer(LabelAndSwitchButton):
    def __init__(self, config_desc, config, key):
        super().__init__(config_desc, config, key)
        # An explicit CLI/config opt-in can enable MCP independently of saved settings.
        if og.ok is not None:
            with QSignalBlocker(self.switch_button):
                self.switch_button.setChecked(og.ok._mcp_server is not None)

    def check_changed(self, checked):
        if checked:
            dialog = MessageBox(
                self.tr('Enable MCP Server?'),
                self.tr('MCP lets local coding agents control this app and execute Python code '
                        'with your account permissions, including reading and changing files. '
                        'Only connect trusted agents and keep the connection token private. '
                        'Enable the server now?'),
                self.window(),
            )
            if not dialog.exec():
                self._restore_switch(False)
                return
        try:
            og.ok.set_mcp_enabled(checked)
        except Exception as error:
            self._restore_switch(not checked)
            dialog = MessageBox(self.tr('MCP server error'), str(error), self.window())
            dialog.cancelButton.hide()
            dialog.exec()

    def _restore_switch(self, checked):
        with QSignalBlocker(self.switch_button):
            self.switch_button.setChecked(checked)
