from ok.config.Config import Config
from ok.config.ConfigOption import ConfigOption
from ok.gui.tasks.ConfigCard import ConfigCard


class GlobalConfigCard(ConfigCard):
    def __init__(self, config: Config, option: ConfigOption):
        super().__init__(option.name, config, option.description, option.default_config, option.config_description,
                         option.config_type, option.icon)

    def reset_clicked(self):
        self.config.reset_to_default()
        self.update_config()
