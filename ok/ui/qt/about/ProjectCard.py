from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QFontMetrics
from PySide6.QtWidgets import QSizePolicy
from qfluentwidgets import SettingCard, FluentIcon, PushButton


class ProjectCard(SettingCard):
    def __init__(self, name, url, website=None, parent=None):
        super().__init__(FluentIcon.GITHUB, name, url)
        self.setParent(parent)
        self.url = url
        self.iconLabel.hide()  # Remove icon as per user request
        self.contentLabel.setMinimumWidth(0)
        self.contentLabel.setMaximumWidth(150)
        self.contentLabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.contentLabel.setText(QFontMetrics(self.contentLabel.font()).elidedText(
            url, Qt.TextElideMode.ElideMiddle, 320
        ))
        self.contentLabel.setToolTip(url)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for label in (self.titleLabel, self.contentLabel):
            font = label.font()
            font.setPointSize(7)
            label.setFont(font)
        self.hBoxLayout.setSpacing(6)
        self.github_button = PushButton(self.tr("GitHub"), self, icon=FluentIcon.GITHUB)
        self.github_button.clicked.connect(self.open_url)
        self.hBoxLayout.addWidget(self.github_button)
        self.website = website
        if website:
            self.download_button = PushButton(self.tr("Download"), self, icon=FluentIcon.DOWNLOAD)
            self.download_button.clicked.connect(self.open_website)
            self.hBoxLayout.addWidget(self.download_button)
        self.hBoxLayout.addSpacing(11)
        self.setFixedHeight(72)

    def open_url(self):
        QDesktopServices.openUrl(QUrl(self.url))

    def open_website(self):
        QDesktopServices.openUrl(QUrl(self.website))
