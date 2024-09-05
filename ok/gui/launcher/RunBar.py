from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from qfluentwidgets import PushButton, ComboBox

from ok.gui.Communicate import communicate
from ok.gui.util.Alert import alert_error
from ok.logging.Logger import get_logger
from ok.update.GitUpdater import GitUpdater

logger = get_logger(__name__)


class RunBar(QWidget):

    def __init__(self, updater: GitUpdater):
        super().__init__()

        self.updater = updater

        self.layout = QHBoxLayout()

        self.profile_layout = QHBoxLayout()
        self.profile_layout.setSpacing(6)

        self.layout.addLayout(self.profile_layout, stretch=0)
        self.profile_label = QLabel(self.tr("Choose Profile:"))
        self.profile_layout.addWidget(self.profile_label, stretch=0)

        self.profiles = ComboBox()
        self.profile_layout.addWidget(self.profiles, stretch=0)
        self.profile_layout.addSpacing(30)

        communicate.launcher_profiles.connect(self.update_profile)

        self.update_profile(None)

        self.run_button = PushButton(self.tr("Run"))
        self.run_button.clicked.connect(self.updater.run)
        self.layout.addWidget(self.run_button, alignment=Qt.AlignRight, stretch=0)

        self.setLayout(self.layout)

        communicate.update_running.connect(self.update_running)
        self.updater.list_all_versions()

    def update_profile(self, profiles):
        profile_names = [profile['name'] for profile in self.updater.launch_profiles]
        self.profiles.addItems(profile_names)
        self.profiles.setText(self.updater.launcher_config.get('profile_name'))

    def update_running(self, running):
        self.profiles.setDisabled(running)
        self.run_button.setEnabled(True if not running and self.updater.launcher_config.get('profile_name') else False)

    def update_clicked(self):
        self.updater.update_to_version(self.version_list.currentText())
        self.update_button.setDisabled(True)

    def clone_version(self, error):
        self.update_button.setDisabled(False)
        if error:
            alert_error(error)
