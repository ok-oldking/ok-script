from PySide6.QtCore import QTimer
from qfluentwidgets import BodyLabel, CheckBox, MessageBoxBase, SubtitleLabel


class ImportWarningDialog(MessageBoxBase):
    """Shared acknowledgement for installing third-party scripts and plugins."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr('Warning'), self)
        self.viewLayout.addWidget(self.titleLabel)
        self.warning_label = BodyLabel(self.tr(
            'Make sure that you trust the script publisher, unverified script can and not limited to steal your account/ data money, destroy your data, harm/ controlling your computer.'), self)
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet('color: red; font-weight: bold;')
        self.viewLayout.addWidget(self.warning_label)
        self.check_box = CheckBox(self.tr('I understand the risks and want to import this script.'), self)
        self.viewLayout.addWidget(self.check_box)
        self.countdown = 15
        self.yesButton.setText(self.tr('Confirm') + f' ({self.countdown})')
        self.yesButton.setEnabled(False)
        self.cancelButton.setText(self.tr('Cancel'))
        self.widget.setMinimumWidth(400)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_countdown)
        self.timer.start(1000)
        self.finished.connect(self.timer.stop)
        self.check_box.stateChanged.connect(self.check_state_changed)

    def update_countdown(self):
        self.countdown -= 1
        if self.countdown > 0:
            self.yesButton.setText(self.tr('Confirm') + f' ({self.countdown})')
        else:
            self.timer.stop()
            self.yesButton.setText(self.tr('Confirm'))
            self.check_state_changed()

    def check_state_changed(self):
        self.yesButton.setEnabled(self.countdown <= 0 and self.check_box.isChecked())
