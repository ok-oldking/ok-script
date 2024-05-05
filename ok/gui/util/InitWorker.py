from PySide6.QtCore import QThread

from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class InitWorker(QThread):

    def __init__(self, fun):
        super().__init__()
        self.fun = fun

    def run(self):
        self.fun()
