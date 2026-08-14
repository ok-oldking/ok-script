import os
import threading

from qfluentwidgets import FluentIcon

from ok.util.config import ConfigOption, Config
from ok.util.file import get_relative_path, read_json_file, write_json_file
from ok.util.logger import Logger

logger = Logger.get_logger("GlobalConfig")

APP_LAUNCHER_OPTION_NAME = 'App Launcher'
APP_LAUNCHER_AUTO_START = 'Auto Start {app_name}'
APP_LAUNCHER_UPDATE_METHOD = 'Auto Update'
APP_LAUNCHER_ACTION = 'Launcher'
APP_LAUNCHER_OPEN = 'Open Launcher'
KILL_LAUNCHER_AFTER_START = 'Kill Launcher After Start'
NOTIFICATION_OPTION_NAME = 'Notification'
SYSTEM_NOTIFICATION_ENABLED = 'System Notification'
DISCORD_NOTIFICATION_ENABLED = 'Discord Notification'
DISCORD_WEBHOOK = 'Discord Webhook'
QQ_NOTIFICATION_ENABLED = 'QQ Desktop Notification (Not Reliable)'
QQ_NICKNAME = 'QQ Desktop Nickname'
WECHAT_NOTIFICATION_ENABLED = 'WeChat Desktop Notification (Not Reliable)'
WECHAT_NICKNAME = 'WeChat Desktop Nickname'
TELEGRAM_NOTIFICATION_ENABLED = 'Telegram Notification'
TELEGRAM_BOT_TOKEN = 'Telegram Bot Token'
TELEGRAM_CHAT_ID = 'Telegram Chat ID'
WECOM_NOTIFICATION_ENABLED = 'Enterprise WeChat Webhook Notification'
WECOM_WEBHOOK = 'Enterprise WeChat Webhook URL'
QQ_BOT_NOTIFICATION_ENABLED = 'QQ Bot API Notification'
QQ_BOT_APP_ID = 'QQ Bot API App ID'
QQ_BOT_TOKEN = 'QQ Bot API Token'
QQ_BOT_CHANNEL_ID = 'QQ Bot API Channel ID'

_LEGACY_NOTIFICATION_KEYS = {
    'QQ Notification': QQ_NOTIFICATION_ENABLED,
    'QQ Desktop Notification': QQ_NOTIFICATION_ENABLED,
    'QQ Nickname': QQ_NICKNAME,
    'WeChat Notification': WECHAT_NOTIFICATION_ENABLED,
    'WeChat Desktop Notification': WECHAT_NOTIFICATION_ENABLED,
    'WeChat Nickname': WECHAT_NICKNAME,
}
UPDATE_METHOD_LABELS = {
    'Manual Update': 'MANUAL_UPDATE',
    'Automatic Update(Release Only)': 'AUTO_UPDATE',
    'Automatic Update (Pre-release)': 'AUTO_UPDATE_PRE_RELEASE',
}
UPDATE_METHOD_VALUES = {value: label for label, value in UPDATE_METHOD_LABELS.items()}

_basic_options_default = {
    'Auto Start Game When App Starts': False,
    'Minimize Window to System Tray when Closing': False,
    'Mute Game while in Background': False,
    'Auto Resize Game Window': True,
    'Exit App when Game Exits': False,
    'Use DirectML': 'Yes',
    'Trigger Interval': 1,
    'Start/Stop': 'F9',
    KILL_LAUNCHER_AFTER_START: True,
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


def create_notification_options():
    default = {
        SYSTEM_NOTIFICATION_ENABLED: True,
        DISCORD_NOTIFICATION_ENABLED: False,
        DISCORD_WEBHOOK: '',
        TELEGRAM_NOTIFICATION_ENABLED: False,
        TELEGRAM_BOT_TOKEN: '',
        TELEGRAM_CHAT_ID: '',
        WECOM_NOTIFICATION_ENABLED: False,
        WECOM_WEBHOOK: '',
        QQ_BOT_NOTIFICATION_ENABLED: False,
        QQ_BOT_APP_ID: '',
        QQ_BOT_TOKEN: '',
        QQ_BOT_CHANNEL_ID: '',
        # Desktop automation is intentionally last and marked unreliable.
        QQ_NOTIFICATION_ENABLED: False,
        QQ_NICKNAME: '',
        WECHAT_NOTIFICATION_ENABLED: False,
        WECHAT_NICKNAME: '',
    }
    config_type = {
        DISCORD_NOTIFICATION_ENABLED: {'sub_configs': {True: [DISCORD_WEBHOOK]}},
        DISCORD_WEBHOOK: {
            'type': 'line_edit', 'minimum_width': 480, 'maximum_width': 640},
        QQ_NOTIFICATION_ENABLED: {'sub_configs': {True: [QQ_NICKNAME]}},
        WECHAT_NOTIFICATION_ENABLED: {'sub_configs': {True: [WECHAT_NICKNAME]}},
        TELEGRAM_NOTIFICATION_ENABLED: {
            'sub_configs': {True: [TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]}},
        WECOM_NOTIFICATION_ENABLED: {'sub_configs': {True: [WECOM_WEBHOOK]}},
        QQ_BOT_NOTIFICATION_ENABLED: {
            'sub_configs': {True: [QQ_BOT_APP_ID, QQ_BOT_TOKEN, QQ_BOT_CHANNEL_ID]}},
        TELEGRAM_BOT_TOKEN: {'type': 'line_edit'},
        TELEGRAM_CHAT_ID: {'type': 'line_edit'},
        WECOM_WEBHOOK: {'type': 'line_edit', 'minimum_width': 480, 'maximum_width': 640},
        QQ_BOT_APP_ID: {'type': 'line_edit'},
        QQ_BOT_TOKEN: {'type': 'line_edit'},
        QQ_BOT_CHANNEL_ID: {'type': 'line_edit'},
    }
    descriptions = {
        SYSTEM_NOTIFICATION_ENABLED: 'Show notifications using the Windows system tray',
        DISCORD_NOTIFICATION_ENABLED: 'Send notifications to a Discord webhook',
        DISCORD_WEBHOOK: 'Discord channel webhook URL',
        QQ_NOTIFICATION_ENABLED: (
            'Requires the local QQ client window to be open and running'),
        QQ_NICKNAME: 'Exact QQ contact nickname',
        WECHAT_NOTIFICATION_ENABLED: (
            'Requires the local WeChat client window to be open and running'),
        WECHAT_NICKNAME: 'Exact WeChat contact nickname',
        TELEGRAM_NOTIFICATION_ENABLED: 'Send notifications through the Telegram Bot API',
        TELEGRAM_BOT_TOKEN: 'Telegram bot token from BotFather',
        TELEGRAM_CHAT_ID: 'Telegram user, group, or channel chat ID',
        WECOM_NOTIFICATION_ENABLED: 'Send notifications through an Enterprise WeChat group bot',
        WECOM_WEBHOOK: 'Enterprise WeChat group bot webhook URL',
        QQ_BOT_NOTIFICATION_ENABLED: 'Send notifications through the QQ Guild Bot API',
        QQ_BOT_APP_ID: 'QQ Bot application ID',
        QQ_BOT_TOKEN: 'QQ Bot application token',
        QQ_BOT_CHANNEL_ID: 'QQ channel ID to receive notifications',
    }
    return ConfigOption(
        NOTIFICATION_OPTION_NAME,
        default,
        description=(
            'Choose where notifications are delivered. Notifications always appear in the app; '
            'enable any additional providers you want to receive them.'),
        config_description=descriptions,
        config_type=config_type,
        icon=FluentIcon.RINGER,
        show_at_tab=True,
    )


notification_options = create_notification_options()


def register_notification_options(global_config):
    # Preserve settings written before API providers were added, when the
    # desktop clients were labelled simply "QQ" and "WeChat".
    path = get_relative_path(Config.config_folder, f'{NOTIFICATION_OPTION_NAME}.json')
    existing = read_json_file(path)
    if isinstance(existing, dict):
        migrated = False
        for old_key, new_key in _LEGACY_NOTIFICATION_KEYS.items():
            if old_key in existing and new_key not in existing:
                existing[new_key] = existing.pop(old_key)
                migrated = True
        if migrated:
            write_json_file(path, existing)
    return global_config.get_config(create_notification_options())


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

    def register_config(self, option, config):
        """Register a config whose storage is managed outside the normal config folder."""
        with self.lock:
            existing = self.configs.get(option.name)
            if existing is not None:
                return existing
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


class AppLauncherConfig(dict):
    """Config adapter that persists launcher preferences through PyAppify."""

    def __init__(self, pyappify_module, launcher_config, basic_config=None):
        self.pyappify_module = pyappify_module
        self.basic_config = basic_config
        self.default = {
            APP_LAUNCHER_AUTO_START: False,
            APP_LAUNCHER_UPDATE_METHOD: UPDATE_METHOD_VALUES['AUTO_UPDATE'],
        }
        super().__init__(self._to_display_config(launcher_config))

    def _to_display_config(self, launcher_config):
        display_config = {
            APP_LAUNCHER_AUTO_START: launcher_config['auto_start'],
            APP_LAUNCHER_UPDATE_METHOD: UPDATE_METHOD_VALUES[launcher_config['update_method']],
        }
        if self.basic_config is not None and KILL_LAUNCHER_AFTER_START in self.basic_config:
            display_config[KILL_LAUNCHER_AFTER_START] = self.basic_config[KILL_LAUNCHER_AFTER_START]
        return display_config

    def get_default(self, key):
        if key == KILL_LAUNCHER_AFTER_START and self.basic_config is not None:
            return self.basic_config.get_default(key)
        return self.default.get(key)

    def has_user_config(self):
        return True

    def reset_to_default(self):
        self._update_launcher(
            auto_start=self.default[APP_LAUNCHER_AUTO_START],
            update_method=UPDATE_METHOD_LABELS[self.default[APP_LAUNCHER_UPDATE_METHOD]],
        )

    def __setitem__(self, key, value):
        if value == self.get(key):
            return
        if key == APP_LAUNCHER_AUTO_START and isinstance(value, bool):
            self._update_launcher(auto_start=value)
        elif key == APP_LAUNCHER_UPDATE_METHOD and value in UPDATE_METHOD_LABELS:
            self._update_launcher(update_method=UPDATE_METHOD_LABELS[value])
        elif key == KILL_LAUNCHER_AFTER_START and isinstance(value, bool) and self.basic_config is not None:
            self.basic_config[key] = value
            super().__setitem__(key, self.basic_config[key])

    def _update_launcher(self, **changes):
        try:
            launcher_config = self.pyappify_module.update_app_config(**changes)
            display_config = self._to_display_config(launcher_config)
        except Exception as e:
            logger.error('Failed to update app launcher config', e)
            return False
        super().clear()
        super().update(display_config)
        return True


def create_app_launcher_options(pyappify_module, basic_config=None):
    """Return the launcher option and config only when the new API is usable."""
    get_path = getattr(pyappify_module, 'get_app_json_path', None)
    get_config = getattr(pyappify_module, 'get_app_config', None)
    update_config = getattr(pyappify_module, 'update_app_config', None)
    if not all(callable(function) for function in (get_path, get_config, update_config)):
        return None

    try:
        config_path = get_path()
        if not config_path or not os.path.isfile(config_path):
            return None
        launcher_config = get_config()
        if (
            not isinstance(launcher_config, dict)
            or not isinstance(launcher_config.get('auto_start'), bool)
            or launcher_config.get('update_method') not in UPDATE_METHOD_VALUES
        ):
            return None
    except Exception as e:
        logger.error('PyAppify app launcher config is unavailable', e)
        return None

    config_type = {
        APP_LAUNCHER_UPDATE_METHOD: {
            'type': 'drop_down',
            'options': list(UPDATE_METHOD_LABELS),
        },
    }
    show_launcher = getattr(pyappify_module, 'show_pyappify', None)
    if callable(show_launcher):
        config_type[APP_LAUNCHER_ACTION] = {
            'type': 'button',
            'text': APP_LAUNCHER_OPEN,
            'icon': FluentIcon.UPDATE,
            'callback': show_launcher,
        }

    option = ConfigOption(
        APP_LAUNCHER_OPTION_NAME,
        {},
        description='Configure the app launcher',
        config_description={
            APP_LAUNCHER_AUTO_START: 'Start the launcher automatically when you sign in',
            APP_LAUNCHER_UPDATE_METHOD: 'Choose how the launcher installs updates',
            APP_LAUNCHER_ACTION: 'Open the app launcher to manage updates',
        },
        config_type=config_type,
        icon=FluentIcon.APPLICATION,
    )
    return option, AppLauncherConfig(pyappify_module, launcher_config, basic_config)


def register_app_launcher_options(global_config, pyappify_module):
    basic_config = global_config.configs.get('Basic Options')
    launcher_options = create_app_launcher_options(pyappify_module, basic_config)
    if launcher_options is None:
        return None
    if basic_config is not None:
        basic_option = global_config.config_options.get('Basic Options')
        if basic_option is not None:
            if basic_option.config_type is None:
                basic_option.config_type = {}
            basic_option.config_type[KILL_LAUNCHER_AFTER_START] = {'hidden': True}
    option, config = launcher_options
    return global_config.register_config(option, config)
