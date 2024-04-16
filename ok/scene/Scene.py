from abc import abstractmethod

from ok.logging.Logger import get_logger
from ok.task.ExecutorOperation import ExecutorOperation


class Scene(ExecutorOperation):
    name = None

    def __init__(self):
        self.name = self.__class__.__name__
        self.logger = get_logger(self.__class__.__name__)

    @abstractmethod
    def detect(self, frame):
        return False
