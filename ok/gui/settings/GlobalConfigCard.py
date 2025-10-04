from ok import Config
from ok import ConfigOption
from ok.gui.tasks.ConfigCard import ConfigCard


class GlobalConfigCard(ConfigCard):
    def __init__(self, config: Config, option: ConfigOption):
        super().__init__(None, option.name, config, option.description, option.default_config, option.config_description,
                         option.config_type, option.icon)

    def reset_clicked(self):
        self.config.reset_to_default()
        self.update_config()

    def has_key(self, key):
        return key in self.config