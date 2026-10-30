import concurrent.futures
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np

import ok.task.TaskExecutor as task_executor_module
from ok.core import code_runner
from ok.core.code_runner import CodeSession, submit_task_call, wait_result
from ok.task.TaskExecutor import TaskExecutor
from ok.task.exceptions import ExecutorBusyException, TaskDisabledException
from ok.task.task import BaseTask
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

WAIT = 2


class FakeOnetimeTask:
    def __init__(self, name, run=None):
        self.name = name
        self._enabled = False
        self.running = False
        self.paused = False
        self.start_time = 0
        self.exit_after_task = False
        self.config = {}
        self.sleep_check_interval = -1
        self.run = run or (lambda: None)

    @property
    def enabled(self):
        return self._enabled

    def disable(self):
        self._enabled = False

    def on_destroy(self):
        pass


class FakeTriggerTask(FakeOnetimeTask):
    def __init__(self, name, run):
        super().__init__(name, run)
        self._enabled = True
        self.trigger_interval = 0
        self.last_trigger_time = 0

    def should_trigger(self):
        return True


def make_test_executor(device_capture, device_interaction):
    """A paused TaskExecutor without devices, OCR or config, whose thread starts on demand."""
    executor = TaskExecutor.__new__(TaskExecutor)
    executor.lock = threading.Lock()
    executor._wake_condition = threading.Condition()
    executor._wake_version = 0
    executor._destroy_lock = threading.Lock()
    executor._destroyed = False
    executor.exit_event = threading.Event()
    executor.current_task = None
    executor.current_job = None
    executor._job_queue = []
    executor._exclusive_owner = None
    executor.onetime_tasks = []
    executor.onetime_task_queue = []
    executor.trigger_tasks = []
    executor.trigger_task_index = -1
    executor.thread = None
    executor.paused = True
    executor.pause_start = time.time()
    executor.pause_end_time = time.time()
    executor.debug_mode = False
    executor._frame = None
    executor._last_frame_time = 0
    executor.scene = None
    executor.blur_overlay_processor = None
    executor.basic_options = {'Trigger Interval': 0}
    executor.device_manager = SimpleNamespace(
        capture_method=device_capture, interaction=device_interaction,
        get_preferred_device=lambda: {'imei': 'device'})
    return executor


class ExecutorJobTestCase(unittest.TestCase):
    def setUp(self):
        self.device_capture = SimpleNamespace(name='device', connected=lambda: True,
                                              get_frame=lambda busy_wait=0: np.zeros((20, 20, 3), np.uint8))
        self.device_interaction = SimpleNamespace(name='device', should_capture=lambda: True, on_run=Mock(),
                                                  on_destroy=Mock())
        self.executor = make_test_executor(self.device_capture, self.device_interaction)
        patcher = patch.object(task_executor_module, 'prevent_sleeping')
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.executor.stop()
        if self.executor.thread is not None:
            self.executor.thread.join(WAIT)

    def start_unpaused(self):
        with patch.object(task_executor_module.communicate.executor_paused, 'emit'):
            self.executor.start()


class TestExecutorJobs(ExecutorJobTestCase):
    def test_snapshot_copy_does_not_block_executor_jobs(self):
        copying = threading.Event()
        release = threading.Event()
        frame = np.zeros((20, 30, 3), dtype=np.uint8)

        def slow_copy():
            copying.set()
            if not release.wait(5):
                raise TimeoutError('Snapshot copy was not released')
            return frame.copy()

        self.executor._frame_snapshot = (SimpleNamespace(copy=slow_copy), 123.0)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            snapshot = pool.submit(self.executor.get_frame_snapshot)
            try:
                self.assertTrue(copying.wait(WAIT))
                # Job submission and execution must remain available while an
                # observation thread copies the previous frame.
                work = pool.submit(lambda: self.executor.submit(lambda: 42).future.result(WAIT))
                self.assertEqual(work.result(WAIT), 42)
            finally:
                release.set()
            copied_frame, captured_at = snapshot.result(WAIT)
        self.assertEqual(captured_at, 123.0)
        self.assertTrue(np.array_equal(copied_frame, frame))
        self.assertFalse(np.shares_memory(copied_frame, frame))

    def test_job_runs_on_executor_thread_while_paused(self):
        def job():
            self.executor.sleep(0.01)
            return threading.current_thread()

        thread = self.executor.submit(job).future.result(WAIT)

        self.assertIs(self.executor.thread, thread)
        self.assertTrue(self.executor.paused)

    def test_job_can_capture_frame_while_paused(self):
        frame = self.executor.submit(lambda: self.executor.frame).future.result(WAIT)

        self.assertEqual((20, 20, 3), frame.shape)

    def test_job_exception_is_set_on_future(self):
        def job():
            raise ValueError('boom')

        future = self.executor.submit(job).future

        with self.assertRaises(ValueError):
            future.result(WAIT)
        self.assertEqual(1, self.executor.submit(lambda: 1).future.result(WAIT))

    def test_cancel_running_job_stops_at_next_sleep(self):
        started = threading.Event()

        def job():
            started.set()
            while True:
                self.executor.sleep(0.02)

        job_handle = self.executor.submit(job)
        self.assertTrue(started.wait(WAIT))
        self.assertTrue(job_handle.cancel())

        with self.assertRaises(TaskDisabledException):
            job_handle.future.result(WAIT)
        self.assertEqual('next', self.executor.submit(lambda: 'next').future.result(WAIT))

    def test_cancel_queued_job(self):
        release = threading.Event()
        first = self.executor.submit(release.wait)
        second = self.executor.submit(lambda: 'never')

        self.assertTrue(second.cancel())
        release.set()

        self.assertTrue(first.future.result(WAIT))
        self.assertTrue(second.future.cancelled())

    def test_overrides_apply_only_to_job_thread(self):
        capture = SimpleNamespace(name='override', connected=lambda: True)
        interaction = SimpleNamespace(name='override', should_capture=lambda: True)
        inside = threading.Event()
        release = threading.Event()

        def job():
            inside.set()
            release.wait(WAIT)
            return self.executor.method.name, self.executor.interaction.name

        job_handle = self.executor.submit(job, capture=capture, interaction=interaction)
        self.assertTrue(inside.wait(WAIT))
        self.assertEqual('device', self.executor.method.name)
        release.set()

        self.assertEqual(('override', 'override'), job_handle.future.result(WAIT))
        self.assertEqual('device', self.executor.method.name)
        self.assertEqual('device', self.executor.interaction.name)

    def test_job_waits_for_running_onetime_task(self):
        task_started = threading.Event()
        finish_task = threading.Event()
        events = []

        def run():
            task_started.set()
            finish_task.wait(WAIT)
            events.append('task')

        task = FakeOnetimeTask('Task', run)
        task._enabled = True
        self.executor.onetime_tasks = [task]
        with patch.object(task_executor_module.communicate.task, 'emit'), \
                patch.object(task_executor_module.communicate.task_done, 'emit'):
            self.start_unpaused()
            self.assertTrue(task_started.wait(WAIT))
            job = self.executor.submit(lambda: events.append('job'))
            time.sleep(0.1)
            self.assertFalse(job.future.done())
            finish_task.set()
            job.future.result(WAIT)

        self.assertEqual(['task', 'job'], events)

    def test_submit_after_exit_is_cancelled(self):
        self.executor.exit_event.set()

        self.assertTrue(self.executor.submit(lambda: 1).future.cancelled())

    def test_debug_mode_still_ignores_pause_on_any_thread(self):
        self.executor.debug_mode = True

        self.assertFalse(self.executor.blocked_by_pause())


class TestExecutorExclusive(ExecutorJobTestCase):
    def test_acquire_disables_onetime_tasks_and_refuses_other_owners(self):
        task = FakeOnetimeTask('Task')
        task._enabled = True
        self.executor.onetime_tasks = [task]

        with patch.object(task_executor_module.communicate.executor_exclusive, 'emit') as emit:
            self.assertTrue(self.executor.acquire_exclusive('agent'))
            self.assertFalse(self.executor.acquire_exclusive('agent'))
            with self.assertRaises(ExecutorBusyException):
                self.executor.acquire_exclusive('other')

        emit.assert_called_once_with('agent')
        self.assertFalse(task.enabled)
        with self.assertRaises(ExecutorBusyException):
            self.executor.submit(lambda: 1)
        self.assertEqual(1, self.executor.submit(lambda: 1, owner='agent').future.result(WAIT))

    def test_acquire_cancels_other_owners_jobs(self):
        started = threading.Event()

        def job():
            started.set()
            while True:
                self.executor.sleep(0.02)

        running = self.executor.submit(job)
        self.assertTrue(started.wait(WAIT))
        queued = self.executor.submit(lambda: 'never')

        with patch.object(task_executor_module.communicate.executor_exclusive, 'emit'):
            self.executor.acquire_exclusive('agent')

        with self.assertRaises(TaskDisabledException):
            running.future.result(WAIT)
        self.assertTrue(queued.future.cancelled())

    def test_trigger_tasks_are_skipped_until_release(self):
        ran = threading.Event()
        trigger = FakeTriggerTask('Trigger', lambda: ran.set())
        self.executor.trigger_tasks = [trigger]
        self.executor.next_frame = lambda time_out=6: np.zeros((20, 20, 3), np.uint8)
        self.start_unpaused()
        self.assertTrue(ran.wait(WAIT))

        with patch.object(task_executor_module.communicate.executor_exclusive, 'emit'):
            self.executor.acquire_exclusive('agent')
            time.sleep(0.1)
            ran.clear()
            time.sleep(0.2)
            self.assertFalse(ran.is_set())
            self.assertTrue(trigger.enabled)

            self.executor.release_exclusive('agent')
        self.assertTrue(ran.wait(WAIT))

    def test_running_trigger_task_stops_when_acquired(self):
        self.executor.thread = threading.current_thread()
        self.executor.current_task = FakeTriggerTask('Trigger', lambda: None)
        self.executor._exclusive_owner = 'agent'

        try:
            with self.assertRaises(TaskDisabledException):
                self.executor.check_enabled(check_pause=False)
            self.assertTrue(self.executor.current_task.enabled)
        finally:
            self.executor.thread = None

    def test_release_cancels_owner_jobs(self):
        release = threading.Event()
        with patch.object(task_executor_module.communicate.executor_exclusive, 'emit'):
            self.executor.acquire_exclusive('agent')
            blocker = self.executor.submit(release.wait, owner='agent')
            queued = self.executor.submit(lambda: 'never', owner='agent')

            self.assertFalse(self.executor.release_exclusive('other'))
            self.assertTrue(self.executor.release_exclusive('agent'))
        release.set()

        blocker.future.result(WAIT)
        self.assertTrue(queued.future.cancelled())
        self.assertIsNone(self.executor.exclusive_owner)

    def test_base_task_enable_refused_while_held(self):
        executor = SimpleNamespace(scene=None, exclusive_owner='agent')
        task = BaseTask(executor, SimpleNamespace(tr=lambda message: message))

        with patch('ok.task.task.alert_error') as alert, \
                patch('ok.task.task.communicate.task.emit'):
            task.enable()

        self.assertFalse(task.enabled)
        alert.assert_called_once()

    def test_start_controller_refused_while_held(self):
        from ok.core import start_controller as start_controller_module
        controller = start_controller_module.StartController.__new__(start_controller_module.StartController)
        og = SimpleNamespace(executor=SimpleNamespace(exclusive_owner='agent'), app=None)

        with patch.object(start_controller_module, 'og', og), \
                patch.object(start_controller_module.communicate.starting_emulator, 'emit') as emit:
            self.assertFalse(controller._do_start())

        self.assertTrue(emit.call_args.args[0])
        self.assertIn('agent', emit.call_args.args[1])


class TestCodeRunner(ExecutorJobTestCase):
    def setUp(self):
        super().setUp()
        self.session = CodeSession(self.executor)

    def test_last_expression_is_value_and_namespace_persists(self):
        first = self.session.run('x = 2\ndef double():\n    return x * 2\nx + 1', timeout=WAIT)
        second = self.session.run('double()', timeout=WAIT)

        self.assertTrue(first.ok, first.error)
        self.assertEqual('3', first.value)
        self.assertEqual('4', second.value)

    def test_reset_clears_namespace(self):
        self.session.run('x = 1', timeout=WAIT)
        self.session.reset()

        result = self.session.run('x', timeout=WAIT)

        self.assertIn('NameError', result.error)

    def test_captures_print_and_log_from_job_only(self):
        original_stdout = sys.stdout
        outside = threading.Event()

        def print_elsewhere():
            print('outside job')
            outside.set()

        code = ('print("hello")\n'
                'from ok.util.logger import Logger\n'
                'Logger.get_logger("t").info("logged")\n'
                'import threading\n'
                f'threading.Thread(target=print_elsewhere).start()\n')
        self.session.namespace['print_elsewhere'] = print_elsewhere
        result = self.session.run(code, timeout=WAIT)

        self.assertTrue(outside.wait(WAIT))
        self.assertIn('hello\n', result.output)
        self.assertIn('logged', result.output)
        self.assertNotIn('outside job', result.output)
        self.assertIs(original_stdout, sys.stdout)

    def test_on_output_streams_chunks(self):
        chunks = []

        self.session.run('print("a")\nprint("b")', timeout=WAIT, on_output=chunks.append)

        self.assertEqual('a\nb\n', ''.join(chunks))

    def test_error_traceback_shows_source_line(self):
        result = self.session.run('a = 1\nraise_here = 1 / 0', timeout=WAIT)

        self.assertFalse(result.ok)
        self.assertIn('ZeroDivisionError', result.error)
        self.assertIn('raise_here = 1 / 0', result.error)

    def test_exit_in_code_does_not_stop_executor(self):
        result = self.session.run('exit()', timeout=WAIT)

        self.assertIn('SystemExit', result.error)
        self.assertEqual('1', self.session.run('1', timeout=WAIT).value)

    def test_cancel_marks_result_cancelled(self):
        job = self.session.submit('while True:\n    executor.sleep(0.02)')
        time.sleep(0.1)
        job.cancel()

        result = wait_result(job, WAIT)

        self.assertTrue(result.cancelled)
        self.assertIsNone(result.error)

    def test_timeout_cancels_job(self):
        result = self.session.run('while True:\n    executor.sleep(0.02)', timeout=0.2)

        self.assertTrue(result.cancelled)
        self.assertIn('Timed out', result.error)
        self.assertEqual('1', self.session.run('1', timeout=WAIT).value)

    def test_task_binding(self):
        task = SimpleNamespace(name='T')

        self.assertEqual("'T'", self.session.run('task.name', task=task, timeout=WAIT).value)

    def test_task_call_does_not_evaluate_property_on_caller_thread(self):
        caller = threading.current_thread()
        executor = self.executor

        class Task:
            @property
            def where(self):
                return threading.current_thread() is caller

            def add(self, a, b=0):
                return a + b

        result = wait_result(submit_task_call(executor, Task(), 'where'), WAIT)
        self.assertEqual('False', result.value)
        self.assertEqual('5', wait_result(submit_task_call(executor, Task(), 'add', (2,), {'b': 3}), WAIT).value)
        with self.assertRaises(AttributeError):
            submit_task_call(executor, Task(), 'missing')

    def test_task_call_with_images_uses_image_capture(self):
        import tempfile, os
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, 'shot.png')
        cv2.imwrite(path, np.full((40, 60, 3), 255, np.uint8))
        executor = self.executor

        class Task:
            def size(self):
                frame = executor.frame
                return frame.shape[:2], executor.interaction.__class__.__name__

        result = wait_result(submit_task_call(executor, Task(), 'size', images=[path]), WAIT)

        self.assertTrue(result.ok, result.error)
        self.assertEqual(((40, 60), 'DoNothingInteraction'), result.raw)
        self.assertIs(self.device_capture, executor.method)


if __name__ == '__main__':
    unittest.main()
