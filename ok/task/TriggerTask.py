from ok.logging.Logger import get_logger
from ok.task.BaseTask import BaseTask

logger = get_logger(__name__)


class TriggerTask(BaseTask):

    def __init__(self):
        super().__init__()
        self.default_enable = True
        self.trigger_count = 0

    def on_create(self):
        pass

    def get_status(self):
        if self.enabled:
            return "Enabled"
        else:
            return "Disabled"

    def enable(self):
        super().enable()
        self.config['_enabled'] = True

    def disable(self):
        super().disable()
        self.config['_enabled'] = False
