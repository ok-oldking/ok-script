from qfluentwidgets import FluentIcon, PushButton

from ok.config.Config import Config
from ok.config.ConfigOption import ConfigOption
from ok.gui.tasks.ConfigCard import ConfigCard


class GlobalConfigCard(ConfigCard):
    def __init__(self, config: Config, option: ConfigOption):
        super().__init__(option.name, config, option.description, option.default_config, option.config_description,
                         option.config_type)

        if option.default_config:
            self.reset_config = PushButton(FluentIcon.CANCEL, self.tr("Reset Config"), self)
            self.addWidget(self.reset_config)
            self.reset_config.clicked.connect(self.reset_clicked)

    def reset_clicked(self):
        self.config.reset_to_default()
        self.update_config()
