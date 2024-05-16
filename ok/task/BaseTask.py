from ok.config.Config import Config
from ok.config.InfoDict import InfoDict
from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger
from ok.task.ExecutorOperation import ExecutorOperation

logger = get_logger(__name__)


class BaseTask(ExecutorOperation):

    def __init__(self):
        super().__init__()
        self.logger = get_logger(self.__class__.__name__)
        self.name = self.__class__.__name__
        self.description = ""
        self.feature_set = None
        self._enabled = False
        self.config = None
        self.info = InfoDict()
        self.default_config = {}
        self.config_description = {}
        self.config_type = {}
        self._paused = False

    def pause(self):
        self.executor.pause(self)
        self._paused = True
        communicate.task.emit(self)
        if self.executor.is_executor_thread():
            self.sleep(1)

    def unpause(self):
        self._paused = False
        self.executor.start()
        communicate.task.emit(self)

    @property
    def paused(self):
        return self._paused

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
        if exception is not None:
            if len(exception.args) > 0:
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

    @property
    def enabled(self):
        return self._enabled

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

    def load_config(self, folder):
        self.config = Config(self.default_config, folder, self.__class__.__name__)

    def enable(self):
        if not self._enabled:
            self._enabled = True
            self.info_clear()
        communicate.task.emit(self)

    def disable(self):
        self._enabled = False
        self.executor.current_task = None
        communicate.task.emit(self)

    def get_status(self):
        pass

    def run(self):
        pass

    def on_destroy(self):
        pass

    def set_executor(self, executor):
        self.executor = executor
        self.feature_set = executor.feature_set
        self.load_config(executor.config_folder)
        from ok.task.TriggerTask import TriggerTask
        if isinstance(self, TriggerTask):
            self._enabled = self.config.get('_enabled', self.default_enable)
        self.on_create()
