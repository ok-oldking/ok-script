from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel
from qfluentwidgets import SettingCard, PushButton, ProgressBar, InfoBar, InfoBarPosition

import ok
from ok.gui.Communicate import communicate


class VersionCard(SettingCard):
    """ Sample card """

    def __init__(self, icon, title, version, parent=None):
        super().__init__(icon, title, version)
        self.downloading_text = QLabel()
        self.hBoxLayout.addWidget(self.downloading_text)
        self.hBoxLayout.addSpacing(16)

        self.download_bar = ProgressBar(self)
        self.download_bar.setFixedWidth(80)
        self.download_bar.setFixedHeight(6)
        self.hBoxLayout.addWidget(self.download_bar)
        self.hBoxLayout.addSpacing(16)

        self.check_update_button = PushButton(self.tr("Check for updates"))
        self.check_update_button.clicked.connect(self.check_update)
        self.hBoxLayout.addWidget(self.check_update_button)
        self.hBoxLayout.addSpacing(16)
        self.update_buttons(0, "")
        communicate.check_update.connect(self.update_update)
        communicate.download_update.connect(self.download_update)

    def download_update(self, percent, progress, done, error):
        self.update_buttons(percent, progress)

    def update_buttons(self, percent, progress):
        if ok.gui.app.updater.downloading:
            self.downloading_text.show()
            self.downloading_text.setText(
                self.tr('Downloading {progress} {percent}%').format(progress=progress, percent=format(percent, '.1f')))
            self.download_bar.show()
            self.download_bar.setValue(percent)
        else:
            self.downloading_text.hide()
            self.download_bar.hide()

    def update_update(self, error):
        title = self.tr('Info')
        if ok.gui.app.updater.latest_release or ok.gui.app.updater.stable_release:
            bar = InfoBar.info
            message = self.tr('Found new version!')
        elif error:
            bar = InfoBar.error
            title = self.tr('Check for update error!')
            message = error
        else:
            bar = InfoBar.info
            message = self.tr("This is the newest version!")
        bar(
            title=title,
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,  # won't disappear automatically
            parent=self
        )
        self.check_update_button.setEnabled(True)

    def check_update(self):
        ok.gui.app.updater.async_run(lambda: ok.gui.app.updater.check_for_updates())
        self.check_update_button.setText(self.tr("Checking for updates"))
        self.check_update_button.setEnabled(False)
