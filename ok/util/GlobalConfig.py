import threading

from qfluentwidgets import FluentIcon

from ok.util.config import ConfigOption, Config

basic_options = ConfigOption('Basic Options', {
    'Auto Start Game When App Starts': False,
    'Minimize Window to System Tray when Closing': False,
    'Mute Game while in Background': False,
    'Auto Resize Game Window': True,
    'Exit App when Game Exits': False,
    'Use DirectML': 'Yes',
    'Trigger Interval': 1,
    'Start/Stop': 'F9',
    'Kill Launcher after Start': False
}, config_type={'Use DirectML': {'type': "drop_down", 'options': ['Auto', 'Yes', 'No']},
                'Start/Stop': {'type': "drop_down", 'options': ['None', 'F9', 'F10', 'F11', 'F12']}}
                             , config_description={'Use DirectML': 'Use GPU to Improve Performance',
                                                   'Start/Stop': 'HotKey',
                                                   'Trigger Interval': 'Increase Delay between Trigger Tasks to Reduce CPU/GPU Usage(Milliseconds)'},
                             icon=FluentIcon.GAME)


class GlobalConfig:
    def __init__(self, config_options):
        self.configs = {}
        self.config_options = {}
        self.lock = threading.Lock()
        if config_options:
            for config_option in config_options:
                self.get_config(config_option)

    def get_config(self, option):
        with self.lock:
            if isinstance(option, str):
                if config := self.configs.get(option):
                    return config
                for config in self.configs.values():
                    if option in config:
                        return config
                raise RuntimeError(f'Can not find global config {option}')
            config = self.configs.get(option.name)
            if config is None:
                config = Config(option.name, option.default_config, validator=option.validator)
                self.configs[option.name] = config
                self.config_options[option.name] = option
            return config

    def get_config_desc(self, key):
        for config_option in self.config_options.values():
            desc_s = config_option.config_description
            if key in desc_s:
                return desc_s

    def get_all_visible_configs(self):
        with self.lock:
            configs = []
            # Filter out keys that start with '_'
            for k, v in self.configs.items():
                if not k.startswith('_'):
                    configs.append((k, v, self.config_options.get(k)))
            return sorted(configs, key=lambda x: x[0])
