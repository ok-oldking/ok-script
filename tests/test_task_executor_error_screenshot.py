import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

import ok.task.TaskExecutor as task_executor_module
from ok.task.TaskExecutor import TaskExecutor, error_screenshot_name
from ok.task.exceptions import CannotFindException


class DailyTask:
    """Stands in for a game task whose display name has an emoji."""

    def __init__(self, run):
        self.name = '📅 Daily Task'
        self.start_time = None
        self.running = False
        self.exit_after_task = False
        self.config = {}
        self.run = run
        self.disable = Mock()
        self.info_set = Mock()
        self.on_destroy = Mock()
        self._app = SimpleNamespace(tr=lambda text: text)


class TestErrorScreenshot(unittest.TestCase):
    def make_executor(self):
        executor = TaskExecutor.__new__(TaskExecutor)
        executor.lock = threading.Lock()
        executor._wake_condition = threading.Condition()
        executor._wake_version = 0
        executor.exit_event = threading.Event()
        executor.current_task = None
        executor.onetime_tasks = []
        executor.onetime_task_queue = []
        executor.trigger_tasks = []
        executor.trigger_task_index = -1
        executor.current_job = None
        executor._job_queue = []
        executor._exclusive_owner = None
        executor.thread = None
        executor.debug_mode = False
        executor.paused = False
        executor._frame = None
        executor._last_frame = None
        executor._last_frame_time = time.time()
        executor._snapshot_enabled = False
        executor.scene = None
        executor.check_enabled = lambda check_pause=True: None
        executor.device_manager = SimpleNamespace(interaction=SimpleNamespace(on_run=Mock()))
        return executor

    def run_task(self, executor, task):
        calls = iter([(task, False, False)])
        executor.next_task = lambda: next(calls, (None, False, False))
        executor._wait_for_activity = lambda *args: executor.exit_event.set()
        with patch.object(task_executor_module.communicate.task, 'emit'), \
                patch.object(task_executor_module.communicate.notification, 'emit'), \
                patch.object(task_executor_module.communicate.screenshot, 'emit') as screenshot, \
                patch.object(task_executor_module, 'prevent_sleeping'):
            executor.execute()
        return screenshot

    def test_error_after_sleep_saves_last_frame_in_error_folder(self):
        executor = self.make_executor()
        frame = np.ones((20, 20, 3), np.uint8)

        def next_frame(time_out=None):
            executor._frame = frame
            executor._last_frame = frame
            return frame

        executor.next_frame = next_frame

        def run():
            # Like wait_combat(): sleep() clears the scene, then the task raises.
            executor.reset_scene(check_enabled=False)
            raise CannotFindException('cant find the f to enter')

        screenshot = self.run_task(executor, DailyTask(run))

        screenshot.assert_called_once()
        saved_frame, name, show_box, _ = screenshot.call_args.args
        self.assertIs(saved_frame, frame)
        self.assertEqual('error/error_DailyTask_CannotFindException', name)
        self.assertTrue(show_box)

    def test_frame_from_previous_task_is_not_used(self):
        executor = self.make_executor()
        executor._last_frame = np.ones((20, 20, 3), np.uint8)
        executor.next_frame = lambda time_out=None: None

        def run():
            raise Exception('boom')

        screenshot = self.run_task(executor, DailyTask(run))

        screenshot.assert_not_called()

    def test_reset_scene_keeps_last_frame(self):
        executor = self.make_executor()
        frame = np.ones((20, 20, 3), np.uint8)
        executor._frame = frame
        executor._last_frame = frame

        executor.reset_scene(check_enabled=False)

        self.assertIsNone(executor._frame)
        self.assertIs(executor._last_frame, frame)

    def test_error_screenshot_name_is_ascii(self):
        task = DailyTask(Mock())

        self.assertEqual('error/error_DailyTask_Exception', error_screenshot_name(task, Exception('x')))


if __name__ == '__main__':
    unittest.main()
