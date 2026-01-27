import heapq
import threading
import time
from dataclasses import dataclass, field

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


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
        self.name = name
        self.exit_event.bind_stop(self)
        self.thread = threading.Thread(target=self._process_tasks, name=name)
        self.thread.start()

    def _process_tasks(self):
        while not self.exit_event.is_set():
            scheduled_task_to_run = None
            with self.condition:
                while not self.task_queue and not self.exit_event.is_set():
                    self.condition.wait(timeout=1.0)  # Wait with a timeout to periodically check exit_event

                if self.exit_event.is_set():
                    break  # Exit outer loop

                if not self.task_queue:  # Still no tasks after wait (e.g. timeout)
                    continue

                now = time.time()
                next_task_info = self.task_queue[0]  # Peek

                if next_task_info.execute_at <= now:
                    scheduled_task_to_run = heapq.heappop(self.task_queue)
                else:
                    timeout = next_task_info.execute_at - now
                    self.condition.wait(timeout=max(0, timeout))  # max(0, timeout) in case now slightly passed
                    continue

            # Lock is released here
            if scheduled_task_to_run:
                if scheduled_task_to_run.task is None:  # Sentinel for stopping
                    logger.debug(f'stopping handler {self.thread.name}')
                    return  # Exit thread

                self.executing = scheduled_task_to_run.task
                try:
                    scheduled_task_to_run.task()
                except Exception as e:
                    logger.error(f'handler {self.thread.name} raised exception: {e}')  # exc_info=True is helpful
                finally:  # Ensure self.executing is cleared
                    self.executing = None
        logger.debug(f'handler {self.thread.name} processing loop finished due to exit event.')

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
        logger.info(f'handler stop raised exception {self.name}')
        with self.condition:
            self.task_queue.clear()
            heapq.heappush(self.task_queue, ScheduledTask(0, None))
            self.condition.notify_all()
