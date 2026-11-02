from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFontMetrics, QIcon
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from ok.ui.qt.about.UpdateCard import ChangeLogView, UpdateCard
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.cards import Card
from ok.ui.qt.kit.feedback import show_toast
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.layout import FlowLayout
from ok.ui.qt.kit.theme import theme
from ok.ui.qt.util.app import get_localized_app_config
from ok.ui.qt.util.pyappify_startup import get_startup_version_change
from ok.util.file import get_path_relative_to_exe
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

# (config key, label, icon); labels come from the old LinksBar translations.
LINKS = (
    ("github", "GitHub", "github"),
    ("download", "Download", "download"),
    ("discord", "Discord", "chat"),
    ("qq_group", "QQ群", "chat"),
    ("qq_channel", "QQ频道", "chat"),
    ("faq", "FAQ", "help"),
    ("share", "Share", "share"),
    ("sponsor", "Sponsor", "heart"),
)


def _link_label(key, text):
    from PySide6.QtCore import QCoreApplication
    return text if key.startswith("qq_") else QCoreApplication.translate("LinksBar", text)


class AboutSection(QWidget):
    """A titled block on the About page; ``widget`` is its content."""

    def __init__(self, title: str, widget: QWidget, card: bool = True, parent=None):
        super().__init__(parent)
        self.widget = widget
        self.titleLabel = Label(title, "subtitle", self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.titleLabel)
        if card:
            frame = Card(self)
            inner = QVBoxLayout(frame)
            inner.setContentsMargins(20, 18, 20, 18)
            inner.addWidget(widget)
            layout.addWidget(frame)
        else:
            layout.addWidget(widget)


class ProjectCard(Card):
    """A related project with its GitHub and download links."""

    def __init__(self, name, url, website=None, parent=None):
        super().__init__(parent, look="inset")
        self.url = url
        self.website = website
        self.title_label = Label(name, "strong", self)
        self.url_label = Label("", "caption", self)
        self.url_label.setToolTip(url)
        self.url_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.url_label.setMinimumWidth(1)
        self._url = url.replace("https://", "")
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self.title_label)
        text.addWidget(self.url_label)
        self.github_button = Button(icon="github", variant="subtle", parent=self)
        self.github_button.setToolTip(_link_label("github", "GitHub"))
        self.github_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.url)))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 10, 12)
        layout.setSpacing(6)
        layout.addLayout(text, 1)
        layout.addWidget(self.github_button)
        self.download_button = None
        if website:
            self.download_button = Button(icon="download", variant="subtle", parent=self)
            self.download_button.setToolTip(_link_label("download", "Download"))
            self.download_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.website)))
            layout.addWidget(self.download_button)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        metrics = QFontMetrics(self.url_label.font())
        self.url_label.setText(metrics.elidedText(self._url, Qt.TextElideMode.ElideMiddle,
                                                  max(40, self.url_label.width())))


class AboutTab(QWidget):
    def __init__(self, config, pyappify_module=None, exit_event=None, parent=None):
        super().__init__(parent)
        if pyappify_module is None:
            import pyappify as pyappify_module
        self.config = config
        self.link_config = config.get('links') or {}
        self.sections = []

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        contents = QWidget()
        contents.setObjectName("scrollContents")
        self.vBoxLayout = QVBoxLayout(contents)
        self.vBoxLayout.setContentsMargins(28, 20, 28, 32)
        self.vBoxLayout.setSpacing(28)
        scroll.setWidget(contents)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self.version_card = self._build_header(config)
        self.vBoxLayout.addWidget(self.version_card)

        self.update_card = None
        if callable(getattr(pyappify_module, 'get_version_list', None)):
            self.update_card = UpdateCard(
                config.get('version'), pyappify_module, exit_event=exit_event,
                download_url=get_localized_app_config(self.link_config, 'download'),
            )
            self._add_section(self.tr("App update"), self.update_card)
        else:
            logger.warning(
                "pyappify.get_version_list is unavailable; update controls are disabled. "
                f"Loaded module: {getattr(pyappify_module, '__file__', type(pyappify_module).__name__)!r}"
            )

        if version_change := get_startup_version_change(pyappify_module):
            notes = ChangeLogView(version_change.content)
            self._add_section(self._startup_version_change_title(version_change), notes)

        if about := config.get('about'):
            about_label = Label("", "body", word_wrap=True)
            about_label.setText(about)
            about_label.setOpenExternalLinks(True)
            about_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            self._add_section(self.tr("Disclaimer"), about_label)

        projects = self._other_projects(config)
        if projects:
            grid_widget = QWidget()
            grid = QGridLayout(grid_widget)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(12)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            for i, project in enumerate(projects):
                grid.addWidget(ProjectCard(project['name'], project['url'], project.get('website'), grid_widget),
                               i // 2, i % 2)
            self._add_section(self.tr("Other Projects"), grid_widget, card=False)

        self.vBoxLayout.addStretch(1)
        theme.install(self)

    # --- sections -------------------------------------------------------------

    def _add_section(self, title, widget, card=True):
        section = AboutSection(title, widget, card)
        self.sections.append(section)
        self.vBoxLayout.addWidget(section)
        return section

    def _build_header(self, config):
        header = Card()
        icon_label = QLabel(header)
        icon_label.setFixedSize(56, 56)
        icon_path = get_path_relative_to_exe(config.get('gui_icon'))
        if icon_path:
            icon_label.setPixmap(QIcon(icon_path).pixmap(QSize(56, 56), header.devicePixelRatioF()))
        title = Label(config.get('gui_title') or "", "title", header)
        from PySide6.QtCore import QCoreApplication
        build = QCoreApplication.translate("VersionCard", 'Debug' if config.get('debug') else 'Release')
        version = Label(f"{config.get('version') or ''} · {build}", "secondary", header)
        text = QVBoxLayout()
        text.setSpacing(4)
        text.addWidget(title)
        text.addWidget(version)

        links = QWidget(header)
        flow = FlowLayout(links, spacing=8)
        self.link_buttons = {}
        for key, label, icon_name in LINKS:
            url = self.get_url(key)
            if not url:
                continue
            button = Button(_link_label(key, label), icon_name, "secondary", "small", parent=links)
            button.clicked.connect(lambda _=False, k=key: self.open_link(k))
            flow.addWidget(button)
            self.link_buttons[key] = button

        layout = QHBoxLayout(header)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(18)
        layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text)
        layout.addSpacing(12)
        layout.addWidget(links, 1, Qt.AlignmentFlag.AlignVCenter)
        return header

    @staticmethod
    def _other_projects(config):
        projects = [
            {"name": "ok-script", "url": "https://github.com/ok-oldking/ok-script", "website": "https://ok-script.com/"},
            {"name": AboutTab.tr_static("ok-script App Template"), "url": "https://github.com/ok-oldking/ok-script-app",
             "website": "https://app.ok-script.com/"},
            {"name": AboutTab.tr_static("Wuthering Waves"), "url": "https://github.com/ok-oldking/ok-wuthering-waves",
             "website": "https://ok-ww.ok-script.com/"},
            {"name": AboutTab.tr_static("Girls' Frontline 2"), "url": "https://github.com/ok-oldking/ok-gf2"},
            {"name": AboutTab.tr_static("Star Resonance"), "url": "https://github.com/Sanheiii/ok-star-resonance",
             "website": "https://ok-script.com/ok-star-resonance/"},
            {"name": AboutTab.tr_static("Duet Night Abyss"), "url": "https://github.com/BnanZ0/ok-duet-night-abyss"},
            {"name": AboutTab.tr_static("Chaos Zero Nightmare"), "url": "https://github.com/baoxin1100/ok-kes",
             "website": "https://ok-script.com/ok-kes/"},
            {"name": AboutTab.tr_static("Onmyoji"), "url": "https://github.com/YunLiuZ/ok-Onmyoji",
             "website": "https://ok-script.com/ok-onmyoji/"},
            {"name": AboutTab.tr_static("Arknights: Endfield"), "url": "https://github.com/AliceJump/ok-end-field",
             "website": "https://ok-script.com/ok-end-field/"},
            {"name": AboutTab.tr_static("Neverness to Everness"),
             "url": "https://github.com/BnanZ0/ok-neverness-to-everness", "website": "https://ok-script.com/ok-nte/"},
            {"name": AboutTab.tr_static("BrownDust II"), "url": "https://github.com/GodRaymond233/ok-bd2"},
            {"name": AboutTab.tr_static("Azur Promilia"), "url": "https://github.com/longer-sausage/OK-AzurPromilia"},
        ]

        def normalize(url):
            return url.strip().lower().rstrip('/') if url else ""

        current = normalize(get_localized_app_config(config.get('links') or {}, 'github'))
        return [project for project in projects if normalize(project['url']) != current]

    @staticmethod
    def tr_static(text):
        from PySide6.QtCore import QCoreApplication
        return QCoreApplication.translate("AboutTab", text)

    # --- links ----------------------------------------------------------------

    def get_url(self, key):
        return get_localized_app_config(self.link_config, key) if self.link_config else None

    def open_link(self, key):
        url = self.get_url(key)
        if key == "share":
            QApplication.clipboard().setText(url)
            from PySide6.QtCore import QCoreApplication
            show_toast(self, QCoreApplication.translate("LinksBar", 'Share Link copied to clipboard'), tone="success")
            return
        QDesktopServices.openUrl(QUrl(url))

    # --- updates --------------------------------------------------------------

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
