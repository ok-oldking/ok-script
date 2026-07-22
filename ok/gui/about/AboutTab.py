from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QWidget, QSizePolicy
from qfluentwidgets import BodyLabel, SettingCardGroup

from ok.gui.about.ProjectCard import ProjectCard
from ok.gui.about.VersionCard import VersionCard
from ok.gui.util.app import get_localized_app_config
from ok.gui.util.pyappify_startup import get_startup_version_change
from ok.gui.widget.Tab import Tab
from ok.util.file import get_path_relative_to_exe


class AboutTab(Tab):
    def __init__(self, config):
        super().__init__()
        self.version_card = VersionCard(config, get_path_relative_to_exe(config.get('gui_icon')),
                                        config.get('gui_title'), config.get('version'),
                                        config.get('debug'), self)
        # The About page uses the same section rhythm as the rest of the app.
        self.add_widget(self.version_card)

        if version_change := get_startup_version_change():
            update_note_label = BodyLabel()
            update_note_label.setText(version_change.content)
            update_note_label.setWordWrap(True)
            update_note_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            update_note_label.setContentsMargins(0, 0, 0, 0)
            self.add_card(self._startup_version_change_title(version_change), update_note_label)

        projects = [
            {"name": "ok-py按键精灵", "url": "https://github.com/ok-oldking/ok-py"},
            {"name": "鸣潮", "url": "https://github.com/ok-oldking/ok-wuthering-waves"},
            {"name": "少前2", "url": "https://github.com/ok-oldking/ok-gf2"},
            {"name": "星痕共鸣", "url": "https://github.com/Sanheiii/ok-star-resonance"},
            {"name": "二重螺旋", "url": "https://github.com/BnanZ0/ok-duet-night-abyss"},
            {"name": "终末地", "url": "https://github.com/AliceJump/ok-end-field"},
            {"name": "异环", "url": "https://github.com/BnanZ0/ok-neverness-to-everness"},
        ]

        def normalize_url(url):
            return url.strip().lower().rstrip('/') if url else ""

        links = config.get('links') or {}
        current_github_norm = normalize_url(get_localized_app_config(links, 'github'))

        filtered_projects = [p for p in projects if normalize_url(p['url']) != current_github_norm]

        if filtered_projects:
            self.group = SettingCardGroup(self.tr("Other Projects"), self)
            
            self.group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            
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

            self.group.addSettingCard(grid_widget)
            self.group.setContentsMargins(0, 0, 0, 0)
            self.add_widget(self.group)

        if about := config.get('about'):
            about_label = BodyLabel()
            about_label.setText(about)
            about_label.setWordWrap(True)
            about_label.setOpenExternalLinks(True)
            about_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            about_label.setContentsMargins(0, 0, 0, 0)

            self.add_card(None, about_label)

        self.vBoxLayout.addStretch(1)

    def _startup_version_change_title(self, version_change):
        if version_change.action == "update":
            title = self.tr("Update success {from_version} -> {to_version}")
        elif version_change.action == "downgrade":
            title = self.tr("Downgrade success {from_version} -> {to_version}")
        else:
            return version_change.title
        return title.format(from_version=version_change.from_version, to_version=version_change.to_version)
