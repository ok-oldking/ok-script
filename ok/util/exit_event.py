import threading

from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class ExitEvent(threading.Event):
    queues = set()

    def bind_queue(self, queue):
        self.queues.add(queue)

    def set(self):
        super(ExitEvent, self).set()
        logger.debug(f"ExitEvent set event empty queues")
        for queue in self.queues:
            queue.put(None)
