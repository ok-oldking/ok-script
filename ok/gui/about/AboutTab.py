from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel
from qfluentwidgets import TextEdit, PushButton, InfoBar, InfoBarPosition, ProgressBar

import ok.gui
from ok.capture.windows.dump import dump_threads
from ok.gui.Communicate import communicate
from ok.gui.about.VersionCard import VersionCard
from ok.gui.widget.Tab import Tab


class AboutTab(Tab):
    def __init__(self, icon, title, version, about):
        super().__init__()
        self.version_card = VersionCard(icon, title, version, self)
        # Create a QTextEdit instance
        self.addWidget(self.version_card, align=Qt.AlignCenter)
        if ok.gui.app.updater.enabled():
            self.update_hbox = QHBoxLayout()
            self.update_hbox.addStretch()
            self.check_update_button = PushButton(self.tr("Check for updates"))
            self.check_update_button.clicked.connect(self.check_update)
            self.update_hbox.addWidget(self.check_update_button)
            self.download_latest_button = PushButton()
            self.download_latest_button.clicked.connect(self.download_latest)

            self.update_hbox.addWidget(self.download_latest_button)
            self.download_stable_button = PushButton(self.tr("Download stable version {version}").format(version=1))
            self.download_stable_button.clicked.connect(self.download_stable)

            self.update_hbox.addWidget(self.download_stable_button)

            self.download_bar = ProgressBar(self)
            self.download_bar.setFixedWidth(80)
            self.update_hbox.addWidget(self.download_bar)

            self.downloading_text = QLabel()
            self.downloading_text.setFixedWidth(200)
            self.update_hbox.addWidget(self.downloading_text)

            self.update_button = PushButton()
            self.update_button.clicked.connect(self.do_update)
            self.update_hbox.addWidget(self.update_button)

            self.update_hbox.addStretch()
            self.addLayout(self.update_hbox)
            communicate.download_update.connect(self.download_update)
            communicate.check_update.connect(self.update_update)

            self.update_update_buttons(0)
        text_edit = TextEdit()
        text_edit.setHtml(about)
        text_edit.setReadOnly(True)

        # Set the layout on the widget
        self.addWidget(text_edit)
        if ok.gui.ok.debug:
            dump_button = PushButton(self.tr("Dump Threads(HotKey:Ctrl+Alt+D)"))
            dump_button.clicked.connect(dump_threads)
            self.addWidget(dump_button)

    def update_update_buttons(self, percent, progress=""):
        if ok.gui.app.updater.latest_release and not ok.gui.app.updater.downloading:
            self.download_latest_button.setText(self.tr("Download latest version {version} ({size})").format(
                version=ok.gui.app.updater.latest_release.get('version'),
                size=ok.gui.app.updater.latest_release.get('readable_size')))
            self.download_latest_button.show()
        else:
            self.download_latest_button.hide()
        if ok.gui.app.updater.stable_release and not ok.gui.app.updater.downloading:
            self.download_stable_button.setText(self.tr("Download stable version {version}  ({size})").format(
                version=ok.gui.app.updater.stable_release.get('version'),
                size=ok.gui.app.updater.stable_release.get('readable_size')))
            self.download_stable_button.show()
        else:
            self.download_stable_button.hide()
        if ok.gui.app.updater.downloading:
            self.downloading_text.show()
            self.downloading_text.setText(
                self.tr('Downloading {progress} {percent}%').format(progress=progress, percent=format(percent, '.1f')))
            self.download_bar.show()
            self.download_bar.setValue(percent)
        else:
            self.downloading_text.hide()
            self.download_bar.hide()
        if ok.gui.app.updater.to_update:
            self.update_button.show()
            self.update_button.setText(self.tr("Update to {version}").format(
                version=ok.gui.app.updater.to_update.get('version')))
            self.download_latest_button.hide()
            self.download_stable_button.hide()
        else:
            self.update_button.hide()

    def do_update(self):
        ok.gui.app.updater.async_run(lambda: ok.gui.app.updater.update())

    def download_update(self, percent, progress, done, error):
        message = ""
        if done:
            if error:
                bar = InfoBar.error
                title = self.tr('Download Error:')
                message = error
            else:
                bar = InfoBar.info
                title = self.tr('Download Complete!')
            bar(
                title=title,
                content=message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,  # won't disappear automatically
                parent=self
            )
        self.update_update_buttons(percent, progress)

    def download_latest(self):
        ok.gui.app.updater.async_run(lambda: ok.gui.app.updater.download(ok.gui.app.updater.latest_release))

    def download_stable(self):
        ok.gui.app.updater.async_run(lambda: ok.gui.app.updater.download(ok.gui.app.updater.stable_release))

    def update_update(self):
        self.check_update_button.setText(
            self.tr("Check for update"))
        self.check_update_button.setEnabled(True)
        if ok.gui.app.updater.latest_release or ok.gui.app.updater.stable_release:
            bar = InfoBar.info
            message = self.tr('Found new version!')
        elif ok.gui.app.updater.error:
            bar = InfoBar.error
            message = self.tr('Found new version!')
        else:
            bar = InfoBar.info
            message = self.tr("This is the newest version!")
        bar(
            title="",
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,  # won't disappear automatically
            parent=self
        )
        self.update_update_buttons(0)

    def check_update(self):
        ok.gui.app.updater.async_run(lambda: ok.gui.app.updater.check_for_updates())
        self.check_update_button.setText(self.tr("Checking for updates"))
        self.check_update_button.setEnabled(False)
