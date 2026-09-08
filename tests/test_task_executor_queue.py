import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import ok.task.TaskExecutor as task_executor_module
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
        executor._wake_condition = threading.Condition()
        executor._wake_version = 0
        executor.exit_event = threading.Event()
        executor.current_task = None
        executor.onetime_tasks = tasks
        executor.onetime_task_queue = []
        executor.trigger_tasks = []
        executor.trigger_task_index = -1
        return executor

    def test_active_sleep_uses_condition_instead_of_millisecond_polling(self):
        executor = self.make_executor([])
        executor.reset_scene = lambda check_enabled=False: None
        executor.check_enabled = lambda check_pause=False: None
        executor.debug_mode = False
        executor.paused = False
        executor.device_manager = SimpleNamespace(
            interaction=SimpleNamespace(should_capture=lambda: True))

        with patch.object(task_executor_module.time, 'sleep') as sleep:
            executor.sleep(0.01)

        sleep.assert_not_called()

    def test_enqueue_wakes_idle_executor(self):
        task = FakeTask('Task')
        executor = self.make_executor([task])
        wake_version = executor._get_wake_version()
        woke = threading.Event()

        waiter = threading.Thread(
            target=lambda: (executor._wait_for_activity(1, wake_version), woke.set()))
        waiter.start()
        time.sleep(0.01)
        task._enabled = True
        executor.enqueue_onetime_task(task)
        waiter.join(timeout=0.2)

        self.assertTrue(woke.is_set())

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

    def test_destroy_is_idempotent(self):
        executor = self.make_executor([])
        task = SimpleNamespace(on_destroy=Mock())
        interaction = SimpleNamespace(on_destroy=Mock())
        executor.onetime_tasks = [task]
        executor.device_manager = SimpleNamespace(interaction=interaction)

        executor.destroy()
        executor.destroy()

        task.on_destroy.assert_called_once_with()
        interaction.on_destroy.assert_called_once_with()

    def test_prepare_one_time_task_before_first_frame(self):
        executor = self.make_executor([])
        interaction = SimpleNamespace(on_run=Mock(), on_destroy=Mock())
        executor.device_manager = SimpleNamespace(interaction=interaction)

        executor._prepare_task_for_run(is_trigger_task=False)

        interaction.on_run.assert_called_once_with()

    def test_prepare_trigger_task_does_not_force_foreground(self):
        executor = self.make_executor([])
        interaction = SimpleNamespace(on_run=Mock())
        executor.device_manager = SimpleNamespace(interaction=interaction)

        executor._prepare_task_for_run(is_trigger_task=True)

        interaction.on_run.assert_not_called()

    def test_one_time_task_prepares_interaction_before_first_frame(self):
        executor = self.make_executor([])
        executor.paused = False
        executor._frame = None
        executor._last_frame_time = time.time()
        executor.reset_scene = lambda check_enabled=True: None
        interaction = SimpleNamespace(on_run=Mock())
        executor.device_manager = SimpleNamespace(interaction=interaction)

        task = SimpleNamespace(
            name="FishingOnce",
            start_time=None,
            running=False,
            exit_after_task=False,
            config={},
            run=Mock(),
            disable=Mock(),
            on_destroy=Mock(),
        )
        events = []
        interaction.on_run.side_effect = lambda: events.append("on_run")
        executor.next_frame = Mock(
            side_effect=lambda time_out=6: events.append("next_frame"))
        task.run.side_effect = lambda: (
            events.append("run"),
            executor.exit_event.set(),
        )
        executor.next_task = lambda: (task, False, False)

        with patch.object(task_executor_module.communicate.task, "emit"), \
                patch.object(task_executor_module.communicate.task_done, "emit"), \
                patch.object(task_executor_module, "prevent_sleeping"):
            executor.execute()

        self.assertEqual(["on_run", "next_frame", "run"], events)


if __name__ == '__main__':
    unittest.main()
