from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSpacerItem, QSizePolicy
from qfluentwidgets import PushButton, ComboBox

from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger
from ok.update.GitUpdater import GitUpdater

logger = get_logger(__name__)


class RunBar(QWidget):

    def __init__(self, updater: GitUpdater):
        super().__init__()

        self.updater = updater

        self.profile_connected = False

        self.layout = QHBoxLayout()

        self.layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.version_label = QLabel(self.tr("Launcher ") + self.updater.launcher_config.get(
            'launcher_version') + "   " +
                                    self.updater.app_config.get("gui_title") + " " + self.updater.launcher_config.get(
            'app_version'))
        self.layout.addWidget(self.version_label)

        self.profile_layout = QHBoxLayout()
        self.profile_layout.setSpacing(6)

        self.layout.addLayout(self.profile_layout, stretch=0)
        self.profile_label = QLabel(self.tr("Choose Profile:"))
        self.profile_layout.addWidget(self.profile_label, stretch=0)

        self.profiles = ComboBox()
        self.profile_layout.addWidget(self.profiles, stretch=0)
        self.profile_layout.addSpacing(30)

        communicate.launcher_profiles.connect(self.update_profile)

        self.run_button = PushButton(self.tr("Start"))
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self.start_clicked)
        self.layout.addWidget(self.run_button, alignment=Qt.AlignRight, stretch=0)

        self.setLayout(self.layout)

        communicate.update_running.connect(self.update_running)
        self.update_profile(None)

    def start_clicked(self):
        self.updater.run()

    def profile_changed_clicked(self):
        self.updater.change_profile(self.profiles.currentText())

    def update_profile(self, profiles):
        if not profiles:
            profiles = self.updater.launch_profiles
        profile_names = [profile['name'] for profile in profiles]

        # Check if the current profiles are different from the new profiles
        current_profiles = [self.profiles.itemText(i) for i in range(self.profiles.count())]

        if profile_names != current_profiles:
            self.profiles.clear()
            self.profiles.addItems(profile_names)

        # Update the text of the profiles
        current_profile_name = self.updater.launcher_config.get('profile_name')

        if self.profiles.currentText() != current_profile_name:
            self.profiles.setCurrentText(current_profile_name)

        if self.updater.launcher_config['app_dependencies_installed']:
            self.run_button.setText(self.tr('Start'))
        else:
            self.run_button.setText(self.tr('Download Dependencies and Start'))
        if not self.profile_connected:
            self.profile_connected = True
            self.profiles.currentTextChanged.connect(self.profile_changed_clicked)

    def update_running(self, running):
        self.profiles.setDisabled(running)
        self.run_button.setEnabled(True if not running and self.updater.launcher_config.get('profile_name') else False)
