from qfluentwidgets import FluentIcon

from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class ConfigOption:

    def __init__(self, name, default=None, description="", config_description=None, config_type=None,
                 validator=None, icon=FluentIcon.INFO):
        self.name = name
        self.description = description
        self.default_config = default or {}
        self.config_description = config_description or {}
        self.config_type = config_type
        self.validator = validator
        self.icon = icon
