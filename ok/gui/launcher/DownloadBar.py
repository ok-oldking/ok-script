from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget, QHBoxLayout, QSpacerItem, QSizePolicy
from qfluentwidgets import ProgressBar

from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class DownloadBar(QWidget):

    def __init__(self):
        super().__init__()

        self.hbox_layout = QHBoxLayout()
        self.setLayout(self.hbox_layout)
        self.hbox_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.download_bar = ProgressBar(self)
        self.download_bar.setFixedWidth(180)
        self.download_bar.setFixedHeight(8)
        self.hbox_layout.addWidget(self.download_bar, alignment=Qt.AlignRight)
        self.hbox_layout.addSpacing(16)

        self.downloading_text = QLabel()
        self.hbox_layout.addWidget(self.downloading_text, alignment=Qt.AlignRight)
        self.hbox_layout.addSpacing(16)

        self.update_buttons(False, 0, 0, 0)
        communicate.update_running.connect(self.update_running)
        communicate.update_download_percent.connect(self.update_buttons)

    def update_running(self, running):
        if not running:
            self.setVisible(False)

    def update_buttons(self, downloading, downloaded, total, percent):
        self.setVisible(downloading)
        if downloading > 0:
            self.downloading_text.setText(
                self.tr('Installing {progress} {percent}%').format(
                    progress=downloaded + '/' + total, percent=format(percent * 100, '.1f')))
            self.download_bar.setValue(round(percent * 100))
