from ok.logging.Logger import get_logger
from ok.task.BaseTask import BaseTask

logger = get_logger(__name__)


class OneTimeTask(BaseTask):

    def __init__(self):
        super().__init__()
        self._done = False
        self.running = False

    def get_status(self):
        if self.running:
            return "Running"
        elif self.enabled:
            if self.executor.paused:
                return "Paused"
            else:
                return "In Queue"
        else:
            return "Not Started"

    def enable(self):
        self._done = False
        super().enable()

    @property
    def done(self):
        return self._done

    def set_done(self):
        self._done = True
        self.disable()
