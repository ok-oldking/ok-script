import threading
import unittest

from ok.task.TaskExecutor import TaskExecutor


class FakeTask:
    def __init__(self, name):
        self.name = name
        self._enabled = False
        self.running = False

    @property
    def enabled(self):
        return self._enabled


class TestTaskExecutorQueue(unittest.TestCase):
    def make_executor(self, tasks):
        executor = TaskExecutor.__new__(TaskExecutor)
        executor.lock = threading.Lock()
        executor.exit_event = threading.Event()
        executor.current_task = None
        executor.onetime_tasks = tasks
        executor.onetime_task_queue = []
        executor.trigger_tasks = []
        executor.trigger_task_index = -1
        return executor

    def test_onetime_queue_uses_click_order(self):
        task_a = FakeTask("TaskA")
        task_b = FakeTask("TaskB")
        task_c = FakeTask("TaskC")
        executor = self.make_executor([task_a, task_c, task_b])

        task_b._enabled = True
        task_c._enabled = True
        executor.enqueue_onetime_task(task_b)
        executor.enqueue_onetime_task(task_c)

        task, _, is_trigger_task = executor.next_task()
        self.assertIs(task_b, task)
        self.assertFalse(is_trigger_task)

        task, _, is_trigger_task = executor.next_task()
        self.assertIs(task_c, task)
        self.assertFalse(is_trigger_task)

    def test_waiting_for_task_uses_task_in_front(self):
        task_a = FakeTask("TaskA")
        task_b = FakeTask("TaskB")
        task_c = FakeTask("TaskC")
        executor = self.make_executor([task_a, task_b, task_c])

        task_a._enabled = True
        task_a.running = True
        task_b._enabled = True
        task_c._enabled = True
        executor.current_task = task_a
        executor.enqueue_onetime_task(task_b)
        executor.enqueue_onetime_task(task_c)

        self.assertIs(task_a, executor.waiting_for_task(task_b))
        self.assertIs(task_b, executor.waiting_for_task(task_c))

        executor.remove_onetime_task(task_b)
        task_b._enabled = False

        self.assertIs(task_a, executor.waiting_for_task(task_c))

    def test_waiting_for_task_uses_running_trigger_task(self):
        onetime_task = FakeTask("OneTimeTask")
        trigger_task = FakeTask("TriggerTask")
        executor = self.make_executor([onetime_task])

        trigger_task._enabled = True
        trigger_task.running = True
        onetime_task._enabled = True
        executor.current_task = trigger_task
        executor.trigger_tasks = [trigger_task]
        executor.enqueue_onetime_task(onetime_task)

        self.assertIs(trigger_task, executor.waiting_for_task(onetime_task))


if __name__ == '__main__':
    unittest.main()
