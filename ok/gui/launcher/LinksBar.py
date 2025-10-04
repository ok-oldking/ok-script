from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QClipboard
from PySide6.QtWidgets import QWidget, QHBoxLayout, QSpacerItem, QSizePolicy
from qfluentwidgets import FluentIcon, PushButton, BodyLabel

from ok.gui.common.OKIcon import OKIcon
from ok.gui.util.Alert import alert_info


class LinksBar(QWidget):

    def __init__(self, app_config):
        super().__init__()
        self.link_config = app_config.get('links') or {}

        self.layout = QHBoxLayout()

        self.layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.version_label = BodyLabel()
        self.layout.addWidget(self.version_label)
        github_url = self.get_url('github')
        if github_url:
            self.github_button = PushButton(self.tr("GitHub"), icon=FluentIcon.GITHUB)
            self.github_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(github_url)))
            self.layout.addWidget(self.github_button, alignment=Qt.AlignRight, stretch=0)

        if self.get_url('discord'):
            self.discord_button = PushButton(self.tr("Discord"), icon=OKIcon.DISCORD)
            self.discord_button.clicked.connect(lambda: self.open_url('discord'))
            self.layout.addWidget(self.discord_button, alignment=Qt.AlignRight, stretch=0)

        if self.get_url('qq_group'):
            self.github_button = PushButton("QQ群", icon=FluentIcon.CHAT)
            self.github_button.clicked.connect(lambda: self.open_url('qq_group'))
            self.layout.addWidget(self.github_button, alignment=Qt.AlignRight, stretch=0)

        if self.get_url('qq_channel'):
            self.github_button = PushButton("QQ频道", icon=FluentIcon.CHAT)
            self.github_button.clicked.connect(lambda: self.open_url('qq_channel'))
            self.layout.addWidget(self.github_button, alignment=Qt.AlignRight, stretch=0)

        if self.get_url('faq'):
            self.github_button = PushButton(self.tr("FAQ"), icon=FluentIcon.QUESTION)
            self.github_button.clicked.connect(lambda: self.open_url('faq'))
            self.layout.addWidget(self.github_button, alignment=Qt.AlignRight, stretch=0)

        if self.get_url('share'):
            self.share_button = PushButton(self.tr("Share"), icon=FluentIcon.SHARE)
            self.share_button.clicked.connect(self.share)
            self.layout.addWidget(self.share_button, alignment=Qt.AlignRight, stretch=0)

        if self.get_url('sponsor'):
            self.sponsor_button = PushButton(self.tr("Sponsor"), icon=OKIcon.HEART)
            self.sponsor_button.clicked.connect(lambda: self.open_url('sponsor'))
            self.layout.addWidget(self.sponsor_button, alignment=Qt.AlignRight, stretch=0)

        self.setLayout(self.layout)

    def share(self):
        clipboard = QClipboard()
        text = self.get_url('share')
        clipboard.setText(text)
        alert_info(self.tr('Share Link copied to clipboard'))

    def open_url(self, url_name):
        url = self.get_url(url_name)
        QDesktopServices.openUrl(QUrl(url))

    def get_url(self, url_name):
        if self.link_config:
            from ok.gui.util.app import get_localized_app_config
            return get_localized_app_config(self.link_config, url_name)
