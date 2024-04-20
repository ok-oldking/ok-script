import time

from ok.config.Config import Config
from ok.config.InfoDict import InfoDict
from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger
from ok.task.ExecutorOperation import ExecutorOperation

logger = get_logger(__name__)


class BaseTask(ExecutorOperation):
    _done = False

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.name = self.__class__.__name__
        self.description = ""
        self.enabled = True
        self.running = False
        self.config = None
        self.info = InfoDict()
        self.default_config = {}
        self.last_execute_time = 0

    def log_info(self, message, notify=False):
        self.logger.info(message)
        self.info_set("Log", message)
        if notify:
            self.notification(message)
        communicate.task_info.emit()

    def log_debug(self, message, notify=False):
        self.logger.debug(message)
        if notify:
            self.notification(message)

    def log_error(self, message, exception=None, notify=False):
        self.logger.error(message, exception)
        if exception is not None and len(exception.args) > 0:
            message += exception.args[0]
        else:
            message += str(exception)
        self.info_set("Error", message)
        if notify:
            self.notification(message)
        communicate.task_info.emit()

    @staticmethod
    def notification(message, title=None):
        communicate.notification.emit(title, message)

    def info_clear(self):
        self.info.clear()

    def info_incr(self, key, by=1):
        # If the key is in the dictionary, get its value. If not, return 0.
        value = self.info.get(key, 0)
        # Increment the value
        value += by
        # Store the incremented value back in the dictionary
        self.info[key] = value

    def info_add_to_list(self, key, item):
        value = self.info.get(key, [])
        if isinstance(item, list):
            value += item
        else:
            value.append(item)
        self.info[key] = value

    def info_set(self, key, value):
        self.info[key] = value

    def can_run(self):
        return self.enabled and not self._done

    def load_config(self, folder):
        self.config = Config(self.default_config, folder, self.__class__.__name__)

    def enable(self):
        self.enabled = True
        self.info_clear()
        self.set_done(False)
        communicate.tasks.emit()

    def disable(self):
        self.enabled = False
        communicate.tasks.emit()

    def get_status(self):
        if not self.enabled:
            return "Disabled"
        elif self.done:
            return "Done"
        elif self.enabled and self.executor.paused:
            return "Paused"
        elif self.running or self.enabled and time.time() - self.last_execute_time < 3:
            return "Running"
        else:
            return "In Queue"

    def run_frame(self):
        pass

    def reset(self):
        self._done = False
        pass

    @property
    def done(self):
        return self._done

    def set_done(self, done=True):
        self._done = done
