from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QWidget, QSizePolicy
from qfluentwidgets import BodyLabel, SettingCardGroup, FluentIcon

from ok.gui.about.ProjectCard import ProjectCard
from ok.gui.about.VersionCard import VersionCard
from ok.gui.launcher.UpdateBar import UpdateBar
from ok.gui.util.app import get_localized_app_config
from ok.gui.widget.Tab import Tab
from ok.util.file import get_path_relative_to_exe


class AboutTab(Tab):
    def __init__(self, config, updater):
        super().__init__()
        self.version_card = VersionCard(config, get_path_relative_to_exe(config.get('gui_icon')),
                                        config.get('gui_title'), config.get('version'),
                                        config.get('debug'), self)
        self.updater = updater
        self.vBoxLayout.setSpacing(0)
        # Create a QTextEdit instance
        self.add_widget(self.version_card)
        self.vBoxLayout.addSpacing(12)

        projects = [
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
            
            # --- ADD THIS LINE ---
            # Force the SettingCardGroup to only be as tall as its contents
            self.group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            
            grid_widget = QWidget()
            # You already have this constraint for the inner widget, which is great:
            grid_widget.setSizePolicy(grid_widget.sizePolicy().horizontalPolicy(), QSizePolicy.Fixed)
            
            grid_layout = QGridLayout(grid_widget)
            grid_layout.setContentsMargins(0, 0, 0, 0)
            grid_layout.setHorizontalSpacing(8)
            grid_layout.setVerticalSpacing(8)
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
            about_label.setContentsMargins(0, 0, 0, 0)

            self.add_widget(about_label)

        self.vBoxLayout.addStretch(1)
