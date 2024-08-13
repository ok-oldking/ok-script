import threading

from ok.config.Config import Config
from ok.config.ConfigOption import ConfigOption


class GlobalConfig:
    def __init__(self):
        self.configs = {}
        self.config_options = {}
        self.lock = threading.Lock()

    def get_config(self, option: ConfigOption):
        with self.lock:
            config = self.configs.get(option.name)
            if config is None:
                config = Config(option.name, option.default_config, validator=option.validator)
                self.configs[option.name] = config
                self.config_options[option.name] = option
            return config

    def get_all_visible_configs(self):
        with self.lock:
            configs = []
            # Filter out keys that start with '_'
            for k, v in self.configs.items():
                if not k.startswith('_'):
                    configs.append((k, v, self.config_options.get(k)))
            return sorted(configs, key=lambda x: x[0])
