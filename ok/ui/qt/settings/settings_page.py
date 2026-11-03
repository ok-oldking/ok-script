"""The Settings page: appearance plus every global config option.

A section list on the left jumps to, and follows, the sections on the right.
"""

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ok import og
from ok.ui.qt.common.config import Language, cfg
from ok.ui.qt.kit.cards import SettingGroup, SettingRow
from ok.ui.qt.kit.inputs import ComboBox
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.tabs import TabStrip
from ok.ui.qt.kit.theme import set_style_property, theme
from ok.ui.qt.settings.config_section import ConfigSection, _app_tr
from ok.util.GlobalConfig import APP_LAUNCHER_OPTION_NAME

ANCHOR_WIDTH = 200

# Native names, in the order of the Language enum (AUTO last).
LANGUAGE_NAMES = ['简体中文', '繁體中文', 'English', 'Español', '日本語', '한국어']


def _t(text: str) -> str:
    return QCoreApplication.translate("SettingTab", text)


class AnchorItem(QPushButton):
    def __init__(self, text: str, target: QWidget, parent=None):
        super().__init__(text, parent)
        self.target = target
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(34)
        self.toggled.connect(lambda on: set_style_property(self, "current", on))


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsPage")
        self.sections = []
        self.anchors = []

        self.anchor_group = QButtonGroup(self)
        self.anchor_group.setExclusive(True)
        anchor_column = QVBoxLayout()
        anchor_column.setContentsMargins(0, 0, 0, 0)
        anchor_column.setSpacing(2)
        anchor_column.addWidget(Label(QCoreApplication.translate("MainWindow", "Settings"), "display", self))
        anchor_column.addSpacing(14)
        self.anchor_layout = QVBoxLayout()
        self.anchor_layout.setSpacing(2)
        anchor_column.addLayout(self.anchor_layout)
        anchor_column.addStretch(1)
        anchor_holder = QWidget(self)
        anchor_holder.setFixedWidth(ANCHOR_WIDTH)
        anchor_holder.setLayout(anchor_column)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        contents = QWidget()
        contents.setObjectName("scrollContents")
        self.column = QVBoxLayout(contents)
        self.column.setContentsMargins(0, 62, 16, 40)
        self.column.setSpacing(32)
        self.scroll.setWidget(contents)
        self.scroll.verticalScrollBar().valueChanged.connect(self._sync_anchor)

        self._add_appearance()
        self._add_global_configs()
        self.column.addStretch(1)
        if self.anchors:
            self.anchors[0].setChecked(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 20, 12, 0)
        layout.setSpacing(28)
        layout.addWidget(anchor_holder)
        layout.addWidget(self.scroll, 1)
        theme.install(self)

    # --- sections -------------------------------------------------------------

    def _add_section(self, title: str, widget: QWidget) -> None:
        anchor = AnchorItem(title, widget, self)
        anchor.clicked.connect(lambda: self.scroll_to(widget))
        self.anchor_group.addButton(anchor)
        self.anchor_layout.addWidget(anchor)
        self.anchors.append(anchor)
        self.column.addWidget(widget)

    def _add_appearance(self) -> None:
        group = SettingGroup()
        group.title_label.hide()
        self.theme_tabs = TabStrip()
        for key, text in (("auto", _t('Use system setting')), ("light", _t('Light')), ("dark", _t('Dark'))):
            self.theme_tabs.add_tab(key, text)
        self.theme_tabs.set_current(cfg.theme_mode)
        self.theme_tabs.current_changed.connect(self._set_theme)
        group.add_row(SettingRow(_t('Application Theme'), _t("Change the appearance of the application"),
                                 self.theme_tabs, control_width=360))

        # Language.AUTO wraps QLocale() and can alias another member, so build the
        # list from the members that actually exist.
        languages = list(Language)
        names = [LANGUAGE_NAMES[i] if i < len(LANGUAGE_NAMES) and language.name != 'AUTO'
                 else _t('Use system setting') for i, language in enumerate(languages)]
        self.language_combo = ComboBox(names)
        current = cfg.language
        self.language_combo.setCurrentIndex(languages.index(current) if current in languages else len(languages) - 1)
        self.language_combo.activated.connect(lambda index: cfg.set_language(languages[index]))
        group.add_row(SettingRow(_t('Language'), _t('Set your preferred language'), self.language_combo))

        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(Label(_t('App Config'), "subtitle", section))
        layout.addWidget(group)
        self.appearance_section = section
        self._add_section(_t('App Config'), section)

    def _add_global_configs(self) -> None:
        configs = og.executor.global_config.get_all_visible_configs() if og.executor is not None else []
        configs = sorted(configs, key=lambda item: item[0] != APP_LAUNCHER_OPTION_NAME)
        for name, config, option in configs:
            if getattr(option, 'show_at_tab', False):
                continue
            section = ConfigSection(config, option)
            self.sections.append(section)
            self._add_section(_app_tr(option.name), section)

    # --- navigation -----------------------------------------------------------

    def scroll_to(self, widget: QWidget) -> None:
        self.scroll.verticalScrollBar().setValue(widget.y() - 8)

    def goto_config(self, key) -> None:
        for section in self.sections:
            if section.has_key(key):
                self.scroll_to(section)
                return

    def _sync_anchor(self, value: int) -> None:
        bar = self.scroll.verticalScrollBar()
        if value >= bar.maximum() and self.anchors:
            self.anchors[-1].setChecked(True)
            return
        current = None
        for anchor in self.anchors:
            if anchor.target.y() - 24 <= value:
                current = anchor
        if current is not None:
            current.setChecked(True)

    # --- appearance -----------------------------------------------------------

    def _set_theme(self, key: str) -> None:
        cfg.set_theme_mode(key)
