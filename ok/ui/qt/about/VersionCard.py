import pyappify
from PySide6.QtCore import Qt
from qfluentwidgets import FluentIcon, PushButton, SettingCard

from ok.gui.about.LinksBar import LinksBar


class VersionCard(SettingCard):
    """ Sample card """

    def __init__(self, config, icon, title, version, debug, parent=None, pyappify_module=pyappify):
        super().__init__(icon, title, f'{version} {self.get_type(debug)}')
        self.pyappify_module = pyappify_module
        self._init_update_button()
        links_bar = LinksBar(config)
        self.iconLabel.setFixedSize(36, 36)
        self.hBoxLayout.addWidget(links_bar)

    def get_type(self, debug=None):
        return self.tr('Debug') if debug else self.tr('Release')

    def _init_update_button(self):
        if not getattr(self.pyappify_module, 'app_version', None):
            return

        self.check_update_button = PushButton(FluentIcon.UPDATE, self.tr('Check for updates'), self)
        self.check_update_button.clicked.connect(self._show_pyappify)
        self.hBoxLayout.addWidget(self.check_update_button, 0, Qt.AlignVCenter)

    def _show_pyappify(self):
        show_pyappify = getattr(self.pyappify_module, 'show_pyappify', None)
        if callable(show_pyappify):
            show_pyappify()
