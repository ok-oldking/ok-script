from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from qfluentwidgets import SettingCard, FluentIcon, PushButton


class ProjectCard(SettingCard):
    def __init__(self, name, url, parent=None):
        super().__init__(FluentIcon.GITHUB, name, url)
        self.setParent(parent)
        self.url = url
        self.iconLabel.hide()  # Remove icon as per user request
        self.github_button = PushButton(self.tr("GitHub"), self, icon=FluentIcon.GITHUB)
        self.github_button.clicked.connect(self.open_url)
        self.hBoxLayout.addWidget(self.github_button)
        self.hBoxLayout.addSpacing(16)
        self.setFixedHeight(64)

    def open_url(self):
        QDesktopServices.openUrl(QUrl(self.url))
