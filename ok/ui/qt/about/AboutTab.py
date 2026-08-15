from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QWidget, QSizePolicy
from qfluentwidgets import BodyLabel

from ok.ui.qt.about.ProjectCard import ProjectCard
from ok.ui.qt.about.VersionCard import VersionCard
from ok.ui.qt.about.UpdateCard import ChangeLogView, UpdateCard
from ok.ui.qt.util.app import get_localized_app_config
from ok.ui.qt.util.pyappify_startup import get_startup_version_change
from ok.ui.qt.widget.Tab import Tab
from ok.util.file import get_path_relative_to_exe
from ok.util.logger import Logger


logger = Logger.get_logger(__name__)


class AboutTab(Tab):
    def __init__(self, config, pyappify_module=None, exit_event=None):
        super().__init__()
        if pyappify_module is None:
            import pyappify as pyappify_module
        self.version_card = VersionCard(config, get_path_relative_to_exe(config.get('gui_icon')),
                                        config.get('gui_title'), config.get('version'),
                                        config.get('debug'), self)
        # The About page uses the same section rhythm as the rest of the app.
        self.add_widget(self.version_card)

        self.update_card = None
        if callable(getattr(pyappify_module, 'get_version_list', None)):
            self.update_card = UpdateCard(
                config.get('version'), pyappify_module, self, exit_event=exit_event
            )
            self.add_card(self.tr("App update"), self.update_card)
        else:
            logger.warning(
                "pyappify.get_version_list is unavailable; update controls are disabled. "
                f"Loaded module: {getattr(pyappify_module, '__file__', type(pyappify_module).__name__)!r}"
            )

        if version_change := get_startup_version_change(pyappify_module):
            update_note_label = ChangeLogView(version_change.content)
            update_note_label.setContentsMargins(0, 0, 0, 0)
            self.add_card(self._startup_version_change_title(version_change), update_note_label)

        if about := config.get('about'):
            about_label = BodyLabel()
            about_label.setText(about)
            about_label.setWordWrap(True)
            about_label.setOpenExternalLinks(True)
            about_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            about_label.setContentsMargins(0, 0, 0, 0)

            self.add_card(self.tr("Disclaimer"), about_label)

        projects = [
            {"name": self.tr("ok-py Automation Tool"), "url": "https://github.com/ok-oldking/ok-py"},
            {"name": self.tr("ok-script App Template"), "url": "https://github.com/ok-oldking/ok-script-app"},
            {"name": self.tr("Wuthering Waves"), "url": "https://github.com/ok-oldking/ok-wuthering-waves"},
            {"name": self.tr("Girls' Frontline 2"), "url": "https://github.com/ok-oldking/ok-gf2"},
            {"name": self.tr("Star Resonance"), "url": "https://github.com/Sanheiii/ok-star-resonance"},
            {"name": self.tr("Duet Night Abyss"), "url": "https://github.com/BnanZ0/ok-duet-night-abyss"},
            {"name": self.tr("Chaos Zero Nightmare"), "url": "https://github.com/baoxin1100/ok-kes"},
            {"name": self.tr("Onmyoji"), "url": "https://github.com/YunLiuZ/ok-Onmyoji"},
            {"name": self.tr("Arknights: Endfield"), "url": "https://github.com/AliceJump/ok-end-field"},
            {"name": self.tr("Neverness to Everness"), "url": "https://github.com/BnanZ0/ok-neverness-to-everness"},
        ]

        def normalize_url(url):
            return url.strip().lower().rstrip('/') if url else ""

        links = config.get('links') or {}
        current_github_norm = normalize_url(get_localized_app_config(links, 'github'))

        filtered_projects = [p for p in projects if normalize_url(p['url']) != current_github_norm]

        if filtered_projects:
            grid_widget = QWidget()
            grid_widget.setSizePolicy(grid_widget.sizePolicy().horizontalPolicy(), QSizePolicy.Fixed)
            
            grid_layout = QGridLayout(grid_widget)
            grid_layout.setContentsMargins(0, 0, 0, 0)
            grid_layout.setHorizontalSpacing(12)
            grid_layout.setVerticalSpacing(12)
            grid_layout.setAlignment(Qt.AlignTop)

            for i, project in enumerate(filtered_projects):
                card = ProjectCard(project['name'], project['url'], grid_widget)
                grid_layout.addWidget(card, i // 2, i % 2)

            self.group = self.add_card(self.tr("Other Projects"), grid_widget)

        self.vBoxLayout.addStretch(1)

    def check_for_updates(self):
        if self.update_card is not None:
            self.update_card.check_for_updates()

    def _startup_version_change_title(self, version_change):
        if version_change.action == "update":
            title = self.tr("Update success {from_version} -> {to_version}")
        elif version_change.action == "downgrade":
            title = self.tr("Downgrade success {from_version} -> {to_version}")
        else:
            return version_change.title
        return title.format(from_version=version_change.from_version, to_version=version_change.to_version)
