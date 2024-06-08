from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout
from qfluentwidgets import PushButton, InfoBar, InfoBarPosition

import ok.gui
from ok.gui.Communicate import communicate
from ok.gui.about.VersionCard import VersionCard
from ok.gui.widget.Tab import Tab
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class AboutTab(Tab):
    def __init__(self, icon, title, version, debug, about):
        super().__init__()
        self.version_card = VersionCard(icon, title, version, debug, self)
        # Create a QTextEdit instance
        self.addWidget(self.version_card)
        about_label = QLabel()
        about_label.setText(about)
        about_label.setWordWrap(True)
        about_label.setOpenExternalLinks(True)

        # Set the layout on the widget
        self.addWidget(about_label)
        if ok.gui.app.updater is not None and ok.gui.app.updater.enabled():
            self.download_latest_button = PushButton(self.tr('Download Release'))
            self.download_latest_button.clicked.connect(self.download_latest)
            self.download_latest_debug_button = PushButton(self.tr('Download Debug'))
            self.download_latest_debug_button.clicked.connect(self.download_latest_debug)

            self.latest_hbox = QHBoxLayout()
            self.addLayout(self.latest_hbox)
            self.latest_label = QLabel()
            self.latest_label.setWordWrap(True)
            self.latest_hbox.addWidget(self.latest_label, stretch=1)
            self.download_latest_vbox = QVBoxLayout()
            self.latest_hbox.addLayout(self.download_latest_vbox, stretch=0)
            self.download_latest_vbox.addWidget(self.download_latest_button, stretch=0)
            self.download_latest_vbox.addWidget(self.download_latest_debug_button, stretch=0)
            self.download_latest_vbox.addStretch(1)

            self.download_stable_button = PushButton(self.tr('Download Release'))
            self.download_stable_button.clicked.connect(self.download_stable)
            self.download_stable_debug_button = PushButton(self.tr('Download Debug'))
            self.download_stable_debug_button.clicked.connect(self.download_stable_debug)
            self.stable_hbox = QHBoxLayout()
            self.stable_label = QLabel()
            self.stable_label.setWordWrap(True)
            self.addLayout(self.stable_hbox)
            self.stable_hbox.addWidget(self.stable_label, stretch=1)

            self.download_stable_vbox = QVBoxLayout()
            self.stable_hbox.addLayout(self.download_stable_vbox, stretch=0)
            self.download_stable_vbox.addWidget(self.download_stable_button, stretch=0)
            self.download_stable_vbox.addWidget(self.download_stable_debug_button, stretch=0)
            self.download_stable_vbox.addStretch(1)

            communicate.download_update.connect(self.download_update)
            communicate.check_update.connect(self.update_update)

            self.update_update_buttons()

    def update_update_buttons(self):
        if ok.gui.app.updater.latest_release:
            self.latest_label.setText(self.get_version_text(ok.gui.app.updater.latest_release))
        has_release_asset = ok.gui.app.updater.latest_release is not None and ok.gui.app.updater.latest_release.get(
            'release_asset') is not None
        self.download_latest_button.setVisible(has_release_asset)
        has_release_debug = ok.gui.app.updater.latest_release is not None and ok.gui.app.updater.latest_release.get(
            'debug_asset') is not None
        self.download_latest_debug_button.setVisible(has_release_debug)
        self.latest_label.setVisible(has_release_asset or has_release_debug)

        if ok.gui.app.updater.stable_release:
            self.stable_label.setText(self.get_version_text(ok.gui.app.updater.stable_release))

        has_release_asset = ok.gui.app.updater.stable_release is not None and ok.gui.app.updater.stable_release.get(
            'release_asset') is not None
        self.download_stable_button.setVisible(has_release_asset)
        has_release_debug = ok.gui.app.updater.stable_release is not None and ok.gui.app.updater.stable_release.get(
            'debug_asset') is not None
        self.download_stable_debug_button.setVisible(has_release_debug)
        self.stable_label.setVisible(has_release_asset or has_release_debug)

        self.download_latest_button.setDisabled(ok.gui.app.updater.downloading)
        self.download_stable_button.setDisabled(ok.gui.app.updater.downloading)
        self.download_stable_debug_button.setDisabled(ok.gui.app.updater.downloading)
        self.download_latest_debug_button.setDisabled(ok.gui.app.updater.downloading)

    def update_update(self, error):
        self.update_update_buttons()

    def get_version_text(self, release):
        text = "<h3>{title}: {version}</h3>"
        if release.get('prerelease'):
            title = self.tr('Beta Version')
        else:
            title = self.tr('Stable Version')
        text = text.format(title=title, version=release.get('version'))
        text += "<p>{date}</p>".format(date=release.get('date'))
        text += "<p>{notes}</p>".format(notes=text_to_html_paragraphs(release.get('notes')))
        return text

    def download_update(self, percent, progress, done, error):
        if done:
            if error:
                title = self.tr('Download Error:')
                message = error
                InfoBar.error(
                    title=title,
                    content=message,
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=5000,  # won't disappear automatically
                    parent=self
                )

        self.update_update_buttons()

    @staticmethod
    def download_latest():
        ok.gui.app.updater.async_run(lambda: ok.gui.app.updater.download(ok.gui.app.updater.latest_release, False))

    @staticmethod
    def download_latest_debug():
        ok.gui.app.updater.async_run(lambda: ok.gui.app.updater.download(ok.gui.app.updater.latest_release, True))

    @staticmethod
    def download_stable():
        ok.gui.app.updater.async_run(lambda: ok.gui.app.updater.download(ok.gui.app.updater.stable_release, False))

    @staticmethod
    def download_stable_debug():
        ok.gui.app.updater.async_run(lambda: ok.gui.app.updater.download(ok.gui.app.updater.stable_release, True))


def text_to_html_paragraphs(text):
    # Split the text into lines
    lines = text.split('\n')

    # Wrap each line in a <p> tag and join them
    return ''.join(f'<p>{line}</p>' for line in lines)
