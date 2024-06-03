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
                while self.task_queue and self.task_queue[0].execute_at <= now:
                    scheduled_task = heapq.heappop(self.task_queue)
                    if scheduled_task.task is None:
                        logger.debug(f'stopping handler {self.thread.name}')
                        return
                    try:
                        scheduled_task.task()
                    except Exception as e:
                        logger.error(f'handler {self.thread.name} raised exception', e)

                if self.task_queue:
                    next_time = self.task_queue[0].execute_at
                    timeout = next_time - now
                    if timeout > 0:
                        self.condition.wait(timeout=timeout)

    def post(self, task, delay=0, remove_existing=False):
        with self.condition:
            if remove_existing and len(self.task_queue) > 0:
                for obj in self.task_queue.copy():
                    if obj.task == task:
                        self.task_queue.remove(obj)
                        logger.debug(f'removing duplicate task {task}')
            if delay > 0:
                scheduled_task = ScheduledTask(time.time() + delay, task)
            else:
                scheduled_task = ScheduledTask(0, task)
            heapq.heappush(self.task_queue, scheduled_task)
            self.condition.notify()

    def stop(self):
        heapq.heappush(self.task_queue, ScheduledTask(0, None))
        with self.condition:
            self.condition.notify_all()


# Example usage
if __name__ == "__main__":
    def print_message(message):
        from datetime import datetime
        print(f"{message} at {datetime.now().time()}")


    exit_event = ExitEvent()
    handler = Handler(event=ExitEvent(), name="MyHandlerThread")

    # Post a task to run immediately
    handler.post(lambda: print_message("Immediate task"))

    # Post a task to run after a delay (e.g., 2 seconds)
    handler.post_delayed(lambda: print_message("Delayed task"), 2)

    # Post a function to run immediately
    handler.post(lambda: print_message("Immediate function"))

    # Post a function to run after a delay (e.g., 3 seconds)
    handler.post_delayed(lambda: print_message("Delayed function"), 3)

    # Let the handler run for a while to process the tasks
    time.sleep(5)
    exit_event.set()
