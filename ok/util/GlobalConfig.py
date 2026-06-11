import threading

from qfluentwidgets import FluentIcon

from ok.util.config import ConfigOption, Config

_basic_options_default = {
    'Auto Start Game When App Starts': False,
    'Minimize Window to System Tray when Closing': False,
    'Mute Game while in Background': False,
    'Auto Resize Game Window': True,
    'Exit App when Game Exits': False,
    'Use DirectML': 'Yes',
    'Trigger Interval': 1,
    'Start/Stop': 'F9',
    'Kill Launcher After Start': True,
    'Launch with DX11': False
}
_basic_options_type = {'Use DirectML': {'type': "drop_down", 'options': ['Auto', 'Yes', 'No']},
                       'Start/Stop': {'type': "drop_down", 'options': ['None', 'F9', 'F10', 'F11', 'F12']}}
_basic_options_description = {'Use DirectML': 'Use GPU to Improve Performance',
                              'Start/Stop': 'HotKey',
                              'Trigger Interval': 'Increase Delay between Trigger Tasks to Reduce CPU/GPU Usage(Milliseconds)'}
_blur_options_default = {'Enable Blur': False, 'Blur Algorithm': 'Inpaint', 'Blur Interval': 1}
_blur_options_type = {
    'Enable Blur': {'sub_configs': {True: ['Blur Algorithm', 'Blur Interval']}},
    'Blur Algorithm': {'type': 'drop_down', 'options': ['Blur', 'Inpaint']},
    'Blur Interval': {'min': 0}
}
_blur_options_description = {
    'Enable Blur': 'Blur Game UID etc to enhance OLED life',
    'Blur Algorithm': 'Method used to obscure configured areas',
    'Blur Interval': 'Seconds between processed overlay updates'
}


def create_basic_options(enable_blur=False):
    default = dict(_basic_options_default)
    config_type = dict(_basic_options_type)
    description = dict(_basic_options_description)
    if enable_blur:
        default.update(_blur_options_default)
        config_type.update(_blur_options_type)
        description.update(_blur_options_description)
    return ConfigOption('Basic Options', default, config_type=config_type,
                        config_description=description, icon=FluentIcon.GAME)


basic_options = create_basic_options()


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


def register_basic_options(global_config, enable_blur=False):
    options = create_basic_options(enable_blur=enable_blur)
    config = global_config.get_config(options)
    if enable_blur:
        for key, value in _blur_options_default.items():
            if key not in config:
                config.default[key] = value
                config[key] = value
        registered = global_config.config_options.get(options.name)
        if registered:
            for key, value in _blur_options_default.items():
                registered.default_config.setdefault(key, value)
            registered.config_description.update({
                key: registered.config_description.get(key, value)
                for key, value in _blur_options_description.items()
            })
            if registered.config_type is None:
                registered.config_type = {}
            registered.config_type.update(_blur_options_type)
    return config
