from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel
from qfluentwidgets import SettingCard, PushButton, ProgressBar, InfoBar, InfoBarPosition, MessageBox

import ok
from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger
from ok.update.GitUpdater import convert_size

logger = get_logger(__name__)


class VersionCard(SettingCard):
    """ Sample card """

    def __init__(self, icon, title, version, debug, parent=None):
        super().__init__(icon, title, f'{version} {self.get_type(debug)}')

        if ok.gui.app.updater is not None:
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
            self.update_button = PushButton()
            self.update_button.clicked.connect(self.show_update_dialog)
            self.hBoxLayout.addWidget(self.update_button)
            self.hBoxLayout.addSpacing(16)
            self.update_buttons(0, "")
            communicate.check_update.connect(self.update_update)
            communicate.download_update.connect(self.download_update)

    def download_update(self, percent, progress, done, error):
        if done and not error:
            self.show_update_dialog()
        self.update_buttons(percent, progress)

    def update_buttons(self, percent, downloaded, total):
        self.downloading_text.show()
        self.downloading_text.setText(
            self.tr('Downloading {progress} {percent}%').format(
                progress=convert_size(downloaded) + '/' + convert_size(
                    total), percent=format(percent, '.1f')))
        self.download_bar.setValue(percent)

    def get_type(self, debug=None):
        if debug is None and ok.gui.app.updater.to_update is not None:
            debug = ok.gui.app.updater.to_update.get('debug')
        return self.tr('Debug') if debug else self.tr('Release')

    def show_update_dialog(self):
        title = self.tr('Update Now')
        content = self.tr(
            "Are you sure you want to update to {version} {type}?".format(
                version=ok.gui.app.updater.to_update.get(
                    'version'), type=self.get_type())) + '\n\n' + ok.gui.app.updater.to_update.get(
            'notes')

        w = MessageBox(title, content, self.window())
        w.contentLabel.setMaximumHeight(400)
        w.setContentCopyable(True)
        if w.exec():
            logger.info("user click update")
            self.do_update()

    def do_update(self):
        ok.gui.app.updater.async_run(lambda: ok.gui.app.updater.update())

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
        ok.gui.app.updater.check_for_updates()
        self.check_update_button.setText(self.tr("Checking for updates"))
        self.check_update_button.setEnabled(False)
