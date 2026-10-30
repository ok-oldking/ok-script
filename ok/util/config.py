## Config.py
from ok.util.file import get_relative_path, read_json_file, write_json_file
from ok.util.logger import Logger

logger = Logger.get_logger("Config")


class ConfigOption:

    def __init__(self, name, default=None, description="", config_description=None, config_type=None,
                 validator=None, icon=None, show_at_tab=False):
        self.name = name
        self.description = description
        self.default_config = default or {}
        self.config_description = config_description or {}
        self.config_type = config_type
        self.validator = validator
        self.icon = icon
        self.show_at_tab = show_at_tab


class Config(dict):
    config_folder = 'configs'

    def __init__(self, name, default, folder=None, validator=None):
        """
        Initialize the Config object.

        :param default: Default configuration values.
        :param folder: Folder where the config file is stored.
        :param name: Name of the config file.
        :param validator: Optional function to validate key-value pairs.
        """
        self.default = default
        self.validator = validator
        if folder is None:
            folder = self.config_folder
        self.config_file = get_relative_path(folder, f"{name}.json")

        # Read the config file, if it exists, otherwise use default
        config = read_json_file(self.config_file)
        if config is None:
            self.reset_to_default()
        else:
            super().__init__()
            modified = self.verify_config(config, default)
            if modified:
                self.save_file()
        logger.debug(f'init self.config = {self}')

    def save_file(self):
        """
        Save the current configuration to the file.
        """
        try:
            write_json_file(self.config_file, self)
        except Exception as e:
            logger.error(f'save_file error: {e}')

    def get_default(self, key):
        return self.default.get(key)

    def reset_to_default(self):
        """
        Reset the configuration to the default values.
        """
        super().clear()
        self.update(self.default)
        self.save_file()
        logger.debug(f'reset_to_default self.config = {self}')

    def pop(self, key, default=None):
        """
        Remove and return a value from the configuration.

        :param key: The key to remove.
        :param default: The default value if the key does not exist.
        :return: The removed value.
        """
        result = super().pop(key, default)
        self.save_file()
        return result

    def popitem(self):
        """
        Remove and return the last key-value pair from the configuration.
        """
        result = super().popitem()
        self.save_file()
        return result

    def clear(self):
        """
        Clear all configuration values.
        """
        super().clear()
        self.save_file()

    def __setitem__(self, key, value):
        if value != self.get(key) and self.validate(key, value):
            old_value = self.get(key)
            super().__setitem__(key, value)
            if old_value != value:
                self.save_file()

    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError as e:
            logger.error(f'KeyError: {key} not found in config: {self}')
            raise e

    def has_user_config(self):
        return not all(key.startswith('_') for key in self)

    @staticmethod
    def _matches_default_value_type(default, value):
        """
        数值族键按默认值声明类型校验：bool 必须为 bool，int 禁止 bool 充数，
        float 接受 int|float。其余类型交由任务自定义 validator。
        """
        if isinstance(default, bool):
            return isinstance(value, bool)
        if isinstance(default, int):
            return isinstance(value, int) and not isinstance(value, bool)
        if isinstance(default, float):
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        return True

    def validate(self, key, value):
        """
        Validate a configuration key-value pair.

        :param key: The key to validate.
        :param value: The value to validate.
        :return: True if valid, False otherwise.
        """
        default = self.default.get(key)
        if default is not None and not self._matches_default_value_type(default, value):
            from ok.core.events import communicate
            communicate.config_validation.emit(
                f"配置类型错误: {key} 期望 {type(default).__name__}, 实际 {type(value).__name__}"
            )
            return False
        if self.validator is not None:
            valid, message = self.validator(key, value)
            if not valid:
                from ok.core.events import communicate
                communicate.config_validation.emit(message)
                return False
        return True

    def verify_config(self, current, default_config):
        """
        Verify the configuration against the default configuration.

        :param default_config: The default configuration.
        :return: True if the config was modified, False otherwise.
        """
        modified = any(key not in default_config for key in current)
        verified = {}

        for key in default_config:
            if key not in current or not isinstance(current[key], type(default_config[key])):
                value = default_config[key]
                modified = True
            elif self.validator is not None:
                valid = self.validate(key, current[key])
                if not valid:
                    value = default_config[key]
                    modified = True
                else:
                    value = current[key]
            else:
                value = current[key]
            verified[key] = value

        # Avoid __setitem__ while hydrating the object. __setitem__ persists
        # changes, which previously rewrote the complete JSON file once per
        # key whenever an existing config was loaded.
        dict.clear(self)
        dict.update(self, verified)

        return modified
