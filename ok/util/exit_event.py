import threading

from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class ExitEvent(threading.Event):
    queues = set()
    to_stops = set()

    def bind_queue(self, queue):
        self.queues.add(queue)

    def bind_stop(self, to_stop):
        self.to_stops.add(to_stop)

    def set(self):
        super(ExitEvent, self).set()
        logger.debug(f"ExitEvent set event empty queues {self.queues} to_stops: {self.to_stops}")
        for queue in self.queues:
            queue.put(None)

        for to_stop in self.to_stops:
            to_stop.stop()
