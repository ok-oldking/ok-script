from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel
from qfluentwidgets import PushButton, InfoBar, InfoBarPosition, MessageBox

import ok.gui
from ok.capture.windows.dump import dump_threads
from ok.gui.Communicate import communicate
from ok.gui.about.VersionCard import VersionCard
from ok.gui.widget.Tab import Tab
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class AboutTab(Tab):
    def __init__(self, icon, title, version, about):
        super().__init__()
        self.version_card = VersionCard(icon, title, version, self)
        # Create a QTextEdit instance
        self.addWidget(self.version_card)
        if ok.gui.app.updater.enabled():
            self.download_latest_button = PushButton(self.tr('Download'))
            self.download_latest_button.clicked.connect(self.download_latest)

            self.latest_hbox = QHBoxLayout()
            self.addLayout(self.latest_hbox)
            self.latest_label = QLabel()
            self.latest_label.setWordWrap(True)
            self.latest_hbox.addWidget(self.latest_label, stretch=1)
            self.latest_hbox.addWidget(self.download_latest_button, stretch=0)

            self.download_stable_button = PushButton(self.tr('Download'))
            self.download_stable_button.resize(self.download_stable_button.sizeHint())
            self.download_stable_button.clicked.connect(self.download_stable)
            self.stable_hbox = QHBoxLayout()
            self.stable_label = QLabel()
            self.stable_label.setWordWrap(True)
            self.addLayout(self.stable_hbox)
            self.stable_hbox.addWidget(self.stable_label, stretch=1)
            self.stable_hbox.addWidget(self.download_stable_button, stretch=0)

            communicate.download_update.connect(self.download_update)

            self.update_update_buttons(0)
        about_label = QLabel()
        about_label.setText(about)
        about_label.setWordWrap(True)
        about_label.setOpenExternalLinks(True)

        # Set the layout on the widget
        self.addWidget(about_label)
        if ok.gui.ok.debug:
            dump_button = PushButton(self.tr("Dump Threads(HotKey:Ctrl+Alt+D)"))
            dump_button.clicked.connect(dump_threads)
            self.addWidget(dump_button)

    def update_update_buttons(self, percent, progress=""):
        if ok.gui.app.updater.latest_release:
            self.latest_label.setText(self.get_version_text(ok.gui.app.updater.latest_release))
            self.download_latest_button.show()
            self.latest_label.show()
        else:
            self.latest_label.hide()
            self.download_latest_button.hide()
        if ok.gui.app.updater.stable_release:
            self.stable_label.setText(self.get_version_text(ok.gui.app.updater.stable_release))
            self.stable_label.show()
            self.download_stable_button.show()
        else:
            self.stable_label.hide()
            self.download_stable_button.hide()

        if ok.gui.app.updater.downloading:
            self.download_latest_button.setDisabled(True)
            self.download_stable_button.setDisabled(True)
        else:
            self.download_latest_button.setDisabled(False)
            self.download_stable_button.setDisabled(False)

        if ok.gui.app.updater.to_update:
            if ok.gui.app.updater.to_update.get('release') == ok.gui.app.updater.latest_release:
                self.download_latest_button.setText(self.tr('Update'))
            else:
                self.download_stable_button.setText(self.tr('Update'))
        else:
            self.download_latest_button.setText(self.tr('Download'))
            self.download_stable_button.setText(self.tr('Download'))

    def get_version_text(self, release):
        text = "<h3>{title}: {version} ({size})</h3>"
        if release.get('prerelease'):
            title = self.tr('Beta Version')
        else:
            title = self.tr('Release Version')
        text = text.format(title=title, version=release.get('version'), size=release.get('readable_size'))
        text += "<p>{date}</p>".format(date=release.get('date'))
        text += "<p>{notes}</p>".format(notes=text_to_html_paragraphs(release.get('notes')))
        return text

    def do_update(self):
        ok.gui.app.updater.async_run(lambda: ok.gui.app.updater.update())

    def download_update(self, percent, progress, done, error):
        message = ""
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
            else:
                self.show_update_dialog()

        self.update_update_buttons(percent, progress)

    def show_update_dialog(self):
        title = self.tr('Update Now')
        content = self.tr(
            "Are you sure you want to update to {version}?".format(
                version=ok.gui.app.updater.to_update.get(
                    'version'))) + '\n\n' + ok.gui.app.updater.to_update.get(
            'notes')

        w = MessageBox(title, content, self.window())
        w.setContentCopyable(True)
        if w.exec():
            logger.info("user click update")
            self.do_update()

    def download_latest(self):
        if ok.gui.app.updater.to_update and ok.gui.app.updater.to_update.get(
                'release') == ok.gui.app.updater.latest_release:
            self.show_update_dialog()
        else:
            ok.gui.app.updater.async_run(lambda: ok.gui.app.updater.download(ok.gui.app.updater.latest_release))

    def download_stable(self):
        if ok.gui.app.updater.to_update and ok.gui.app.updater.to_update.get(
                'release') == ok.gui.app.updater.stable_release:
            self.show_update_dialog()
        else:
            ok.gui.app.updater.async_run(lambda: ok.gui.app.updater.download(ok.gui.app.updater.stable_release))


def text_to_html_paragraphs(text):
    # Split the text into lines
    lines = text.split('\n')

    # Wrap each line in a <p> tag and join them
    return ''.join(f'<p>{line}</p>' for line in lines)
