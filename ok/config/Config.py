from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger
from ok.util.json import read_json_file, write_json_file
from ok.util.path import get_relative_path

logger = get_logger(__name__)


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
        if self.validate(key, value):
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

    def validate(self, key, value):
        """
        Validate a configuration key-value pair.

        :param key: The key to validate.
        :param value: The value to validate.
        :return: True if valid, False otherwise.
        """
        if self.validator is not None:
            valid, message = self.validator(key, value)
            if not valid:
                communicate.config_validation.emit(message)
                return False
        return True

    def verify_config(self, current, default_config):
        """
        Verify the configuration against the default configuration.

        :param default_config: The default configuration.
        :return: True if the config was modified, False otherwise.
        """
        modified = False

        # Remove entries that do not exist in default_config
        for key in list(current.keys()):
            if key not in default_config:
                del current[key]
                modified = True

        for key in list(default_config.keys()):
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
            self[key] = value

        return modified
