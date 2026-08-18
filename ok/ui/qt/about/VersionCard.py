from qfluentwidgets import SettingCard

from ok.ui.qt.about.LinksBar import LinksBar


class VersionCard(SettingCard):
    """ Sample card """

    def __init__(self, config, icon, title, version, debug, parent=None):
        super().__init__(icon, title, f'{version} {self.get_type(debug)}')
        links_bar = LinksBar(config)
        self.iconLabel.setFixedSize(36, 36)
        for label in (self.titleLabel, self.contentLabel):
            font = label.font()
            font.setPointSize(7)
            label.setFont(font)
        self.hBoxLayout.addWidget(links_bar)

    def get_type(self, debug=None):
        return self.tr('Debug') if debug else self.tr('Release')
