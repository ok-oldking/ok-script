from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox

from ok.ui.qt.kit.dialogs import Dialog
from ok.ui.qt.kit.theme import set_style_property


class ImportWarningDialog(Dialog):
    """Shared acknowledgement for installing third-party scripts and plugins.

    Confirm unlocks after a 15 second countdown once the risk box is checked.
    """

    def __init__(self, parent=None):
        super().__init__(parent, self.tr('Warning'), self.tr(
            'Make sure that you trust the script publisher, unverified script can and not limited to steal your '
            'account/ data money, destroy your data, harm/ controlling your computer.'), danger=True, width=480)
        self.titleLabel = self.title_label
        self.warning_label = self.message_label
        set_style_property(self.warning_label, "tone", "danger")
        self.check_box = QCheckBox(self.tr('I understand the risks and want to import this script.'), self.panel)
        self.body.addWidget(self.check_box)
        self.yesButton = self.ok_button
        self.cancelButton = self.cancel_button
        self.cancelButton.setText(self.tr('Cancel'))
        self.countdown = 15
        self.yesButton.setText(self.tr('Confirm') + f' ({self.countdown})')
        self.yesButton.setEnabled(False)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_countdown)
        self.timer.start(1000)
        self.accepted.connect(self.timer.stop)
        self.rejected.connect(self.timer.stop)
        self.check_box.toggled.connect(self.check_state_changed)

    def update_countdown(self):
        self.countdown -= 1
        if self.countdown > 0:
            self.yesButton.setText(self.tr('Confirm') + f' ({self.countdown})')
        else:
            self.timer.stop()
            self.yesButton.setText(self.tr('Confirm'))
            self.check_state_changed()

    def check_state_changed(self, *_args):
        self.yesButton.setEnabled(self.countdown <= 0 and self.check_box.isChecked())
