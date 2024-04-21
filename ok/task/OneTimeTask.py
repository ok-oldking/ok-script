from ok.logging.Logger import get_logger
from ok.task.BaseTask import BaseTask

logger = get_logger(__name__)


class OneTimeTask(BaseTask):

    def __init__(self):
        super().__init__()
        self.running = False
        self._done = False
        self._enabled = False

    def get_status(self):
        if self.running:
            return "Running"
        elif self.done:
            return "Done"
        elif self.enabled and self.executor.paused:
            return "Paused"
        else:
            return "In Queue"

    def enable(self):
        super().enable()
        self.set_done(False)

    def reset(self):
        self._done = False

    @property
    def done(self):
        return self._done

    def set_done(self, done=True):
        self._done = done
