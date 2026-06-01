from PySide6.QtWidgets import QFrame, QVBoxLayout
from qfluentwidgets import BodyLabel, TitleLabel, isDarkTheme

from ok import Config, ConfigOption, og
from ok.gui.tasks.ConfigCard import ConfigContentMixin
from ok.gui.widget.Tab import Tab


class GlobalConfigTab(ConfigContentMixin, Tab):
    def __init__(self, config: Config, option: ConfigOption):
        super().__init__()
        self.option = option
        self.titleLabel = TitleLabel(self._translate(option.name), self)
        self.titleLabel.setObjectName('viewTitleLabel')
        self.vBoxLayout.addWidget(self.titleLabel)

        self.descriptionLabel = None
        if option.description:
            self.descriptionLabel = BodyLabel(self._translate(option.description), self)
            self.descriptionLabel.setObjectName('contentLabel')
            self.descriptionLabel.setWordWrap(True)
            self.vBoxLayout.addWidget(self.descriptionLabel)

        self.contentFrame = QFrame(self)
        self.contentFrame.setObjectName('configContentFrame')
        self._apply_content_frame_style()
        self.viewLayout = QVBoxLayout(self.contentFrame)
        self.vBoxLayout.addWidget(self.contentFrame)
        self._init_config_content(
            None,
            config,
            option.default_config,
            option.config_description,
            option.config_type
        )
        self.viewLayout.setContentsMargins(10, 8, 10, 8)

    def _translate(self, text):
        if og.app and hasattr(og.app, 'tr'):
            return og.app.tr(text)
        return self.tr(text)

    def _apply_content_frame_style(self):
        if isDarkTheme():
            border = "rgba(255, 255, 255, 0.08)"
            background = "rgba(255, 255, 255, 0.05)"
        else:
            border = "rgba(0, 0, 0, 0.08)"
            background = "rgba(255, 255, 255, 0.5)"
        self.contentFrame.setStyleSheet(
            "#configContentFrame {"
            f"border: 1px solid {border};"
            "border-radius: 10px;"
            f"background-color: {background};"
            "}"
        )

    def reset_clicked(self):
        self.config.reset_to_default()
        self.update_config()

    def has_key(self, key):
        return key in self.config
