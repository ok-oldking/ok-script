import queue
import threading
import time
from dataclasses import dataclass

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


@dataclass(frozen=True)
class NotificationRequest:
    title: str
    message: str
    images: list


class NotificationPipeline:
    """FIFO worker for external notification providers."""

    def __init__(self, handler, exit_event=None, interval=5):
        self.handler = handler
        self.exit_event = exit_event
        self.interval = interval
        self.queue = queue.Queue()
        self.stop_event = threading.Event()
        self._stop_lock = threading.Lock()
        if exit_event is not None:
            if hasattr(exit_event, 'bind_stop'):
                exit_event.bind_stop(self)
            elif hasattr(exit_event, 'bind_queue'):
                exit_event.bind_queue(self.queue)
        self.thread = threading.Thread(
            target=self._worker, name='notifications', daemon=True)
        self.thread.start()

    def submit(self, title, message, images):
        if self.stop_event.is_set():
            return False
        self.queue.put(NotificationRequest(title, message, images))
        return True

    def stop(self, wait=False, timeout=5):
        with self._stop_lock:
            if not self.stop_event.is_set():
                self.stop_event.set()
                self.queue.put(None)
        if wait and threading.current_thread() is not self.thread:
            self.thread.join(timeout=timeout)
        return not self.thread.is_alive()

    def _worker(self):
        last_sent = 0.0
        while True:
            item = self.queue.get()
            if item is None:
                self.queue.task_done()
                break
            if self.stop_event.is_set():
                self.queue.task_done()
                continue
            try:
                delay = self.interval - (time.monotonic() - last_sent)
                if delay > 0:
                    if self.stop_event.wait(delay):
                        continue
                self.handler(item.title, item.message, item.images)
            except Exception as e:
                logger.error('Notification provider failed', e)
            finally:
                last_sent = time.monotonic()
                self.queue.task_done()
