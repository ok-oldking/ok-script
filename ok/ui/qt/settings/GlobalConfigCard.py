from ok import Config
from ok import ConfigOption
from ok.ui.qt.tasks.ConfigCard import ConfigCard
from ok.ui.qt.common.icons import resolve_icon


class GlobalConfigCard(ConfigCard):
    def __init__(self, config: Config, option: ConfigOption):
        super().__init__(None, option.name, config, option.description, option.default_config, option.config_description,
                         option.config_type, resolve_icon(option.icon))

    def reset_clicked(self):
        self.config.reset_to_default()
        self.update_config()

    def has_key(self, key):
        return key in self.config
