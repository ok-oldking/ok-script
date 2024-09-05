import heapq
import threading
import time
from dataclasses import dataclass, field

from ok.logging.Logger import get_logger
from ok.util.exit_event import ExitEvent

logger = get_logger(__name__)


@dataclass(order=True)
class ScheduledTask:
    execute_at: float
    task: callable = field(compare=False)


class Handler:
    def __init__(self, event: ExitEvent, name=None):
        self.task_queue = []
        self.executing = None
        self.condition = threading.Condition()
        self.exit_event = event
        self.exit_event.bind_stop(self)
        self.thread = threading.Thread(target=self._process_tasks, name=name)
        self.thread.start()

    def _process_tasks(self):
        while not self.exit_event.is_set():
            with self.condition:
                while not self.task_queue:
                    self.condition.wait()

            now = time.time()
            self.condition.acquire()
            if self.task_queue and self.task_queue[0].execute_at <= now:
                scheduled_task = heapq.heappop(self.task_queue)
                self.condition.release()
                if scheduled_task.task is None:
                    logger.debug(f'stopping handler {self.thread.name}')
                    return
                self.executing = scheduled_task.task
                try:
                    scheduled_task.task()
                except Exception as e:
                    logger.error(f'handler {self.thread.name} raised exception', e)
                self.executing = None
            else:
                if self.task_queue:
                    next_time = self.task_queue[0].execute_at
                    timeout = next_time - now
                    if timeout > 0:
                        self.condition.wait(timeout=timeout)
                self.condition.release()

    def post(self, task, delay=0, remove_existing=False, skip_if_running=False):
        with self.condition:
            if self.exit_event.is_set():
                logger.error(f'post handler {self.thread.name} already exits')
                self.condition.notify_all()
                return
            if remove_existing and len(self.task_queue) > 0:
                for obj in self.task_queue.copy():
                    if obj.task == task:
                        self.task_queue.remove(obj)
                        logger.debug(f'removing duplicate task {task}')
            if skip_if_running and self.executing == task:
                logger.debug(f'skipping duplicate task {task}')
                return
            if delay > 0:
                scheduled_task = ScheduledTask(time.time() + delay, task)
            else:
                scheduled_task = ScheduledTask(0, task)
            heapq.heappush(self.task_queue, scheduled_task)
            self.condition.notify_all()
            return True

    def stop(self):
        with self.condition:
            self.task_queue.clear()
            heapq.heappush(self.task_queue, ScheduledTask(0, None))
            self.condition.notify_all()
