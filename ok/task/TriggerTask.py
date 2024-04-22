from ok.logging.Logger import get_logger
from ok.task.BaseTask import BaseTask

logger = get_logger(__name__)


class TriggerTask(BaseTask):

    def __init__(self):
        super().__init__()
        self.default_enable = True

    def after_init(self):
        self._enabled = self.config.get('_enabled', self.default_enable)


    def get_status(self):
        if self.enabled:
            return "Enabled"
        else:
            return "Disabled"

    def enable(self):
        super().enable()
        self.config['_enabled'] = True

    def disable(self):
        super().enable()
        self.config['_enabled'] = False
