import heapq
import threading
import time
from dataclasses import dataclass, field

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


class ExitEvent(threading.Event):
    def __init__(self):
        super().__init__()
        self.queues = set()
        self.to_stops = set()
        self.conditions = set()
        self.bindings_lock = threading.Lock()

    def bind_queue(self, queue):
        wake_now = False
        with self.bindings_lock:
            if self.is_set():
                wake_now = True
            else:
                self.queues.add(queue)
        if wake_now:
            try:
                queue.put(None)
            except Exception as error:
                logger.error(f'ExitEvent late queue wake failed for {queue}: {error}')

    def bind_stop(self, to_stop):
        stop_now = False
        with self.bindings_lock:
            if self.is_set():
                stop_now = True
            else:
                self.to_stops.add(to_stop)
        if stop_now:
            try:
                to_stop.stop()
            except Exception as error:
                logger.error(f'ExitEvent late stop callback failed for {to_stop}: {error}')

    def unbind_stop(self, to_stop):
        with self.bindings_lock:
            self.to_stops.discard(to_stop)

    def bind_condition(self, condition):
        wake_now = False
        with self.bindings_lock:
            if self.is_set():
                wake_now = True
            else:
                self.conditions.add(condition)
        if wake_now:
            with condition:
                condition.notify_all()

    def set(self):
        with self.bindings_lock:
            if self.is_set():
                return
            super().set()
            queues = tuple(self.queues)
            to_stops = tuple(self.to_stops)
            conditions = tuple(self.conditions)
        logger.debug(f"ExitEvent set event empty queues {queues} to_stops: {to_stops}")
        for queue in queues:
            try:
                queue.put(None)
            except Exception as error:
                logger.error(f'ExitEvent queue wake failed for {queue}: {error}')

        for to_stop in to_stops:
            try:
                to_stop.stop()
            except Exception as error:
                logger.error(f'ExitEvent stop callback failed for {to_stop}: {error}')

        for condition in conditions:
            try:
                with condition:
                    condition.notify_all()
            except Exception as error:
                logger.error(f'ExitEvent condition wake failed for {condition}: {error}')


@dataclass(order=True)
class ScheduledTask:
    execute_at: float
    task: callable = field(compare=False)


class Handler:
    def __init__(self, event: ExitEvent, name=None, daemon=False):
        self.task_queue = []
        self.executing = None
        self.condition = threading.Condition()
        self.exit_event = event
        self.name = name
        self._stopped = False
        self.exit_event.bind_stop(self)
        self.thread = threading.Thread(target=self._process_tasks, name=name, daemon=daemon)
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

                now = time.monotonic()
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
            if self._stopped or self.exit_event.is_set():
                logger.error(f'post handler {self.thread.name} already exits')
                self.condition.notify_all()
                return
            if remove_existing and len(self.task_queue) > 0:
                old_size = len(self.task_queue)
                self.task_queue[:] = [obj for obj in self.task_queue if obj.task != task]
                if len(self.task_queue) != old_size:
                    heapq.heapify(self.task_queue)
                    logger.debug(f'removing duplicate task {task}')
            if skip_if_running and self.executing == task:
                logger.debug(f'skipping duplicate task {task}')
                return
            if delay > 0:
                scheduled_task = ScheduledTask(time.monotonic() + delay, task)
            else:
                scheduled_task = ScheduledTask(0, task)
            heapq.heappush(self.task_queue, scheduled_task)
            self.condition.notify_all()
            return True

    def stop(self):
        with self.condition:
            if self._stopped:
                return
            self._stopped = True
            logger.info(f'handler stopping {self.name}')
            self.task_queue.clear()
            heapq.heappush(self.task_queue, ScheduledTask(0, None))
            self.condition.notify_all()
        if hasattr(self.exit_event, 'unbind_stop'):
            self.exit_event.unbind_stop(self)

    def join(self, timeout=None):
        if self.thread is not threading.current_thread():
            self.thread.join(timeout)
