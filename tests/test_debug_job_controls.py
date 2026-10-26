import os
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication
from shiboken6 import delete

import ok.task.TaskExecutor as task_executor_module
import ok.ui.qt.debug.JobControls as job_controls_module
from ok import og
from ok.core.code_runner import CodeSession
from ok.ui.qt.debug.JobControls import JobControls
from test_executor_jobs import FakeOnetimeTask, make_test_executor

WAIT = 2


class TestJobControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        capture = SimpleNamespace(connected=lambda: True,
                                  get_frame=lambda busy_wait=0: np.zeros((20, 20, 3), np.uint8))
        interaction = SimpleNamespace(should_capture=lambda: True, on_run=Mock(), on_destroy=Mock())
        self.executor = make_test_executor(capture, interaction)
        patches = [
            patch.object(task_executor_module, 'prevent_sleeping'),
            patch.object(og, 'executor', self.executor, create=True),
            patch.object(og, 'app', SimpleNamespace(tr=lambda message: message), create=True),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.session = CodeSession(self.executor)
        self.controls = JobControls('Run')
        self.results = []
        self.output = []
        self.controls.finished.connect(self.results.append)
        self.controls.output.connect(self.output.append)

    def tearDown(self):
        self.controls.close()
        self.executor.stop()
        if self.executor.thread is not None:
            self.executor.thread.join(WAIT)

    def process_until(self, condition):
        deadline = time.time() + WAIT
        while time.time() < deadline:
            QApplication.processEvents()
            if condition():
                return True
            time.sleep(0.01)
        return False

    def test_run_streams_output_and_reports_result(self):
        job = self.controls.start(lambda on_output: self.session.submit('print("hi")\n1 + 1', on_output=on_output))

        self.assertIsNotNone(job)
        self.assertFalse(self.controls.run_button.isEnabled())
        self.assertTrue(self.process_until(lambda: self.results))
        self.assertEqual('2', self.results[0].value)
        self.assertEqual('hi\n', ''.join(self.output))
        self.assertTrue(self.controls.run_button.isEnabled())
        self.assertFalse(self.controls.stop_button.isEnabled())

    def test_stop_cancels_running_job(self):
        self.controls.start(lambda on_output: self.session.submit(
            'while True:\n    executor.sleep(0.02)', on_output=on_output))
        self.assertTrue(self.process_until(lambda: self.controls.job.future.running()))

        self.controls.stop()

        self.assertTrue(self.process_until(lambda: self.results))
        self.assertTrue(self.results[0].cancelled)
        self.assertEqual('Cancelled', self.controls.status_label.text())

    def test_waiting_job_can_stop_running_task(self):
        started = threading.Event()

        def run():
            started.set()
            while True:
                self.executor.sleep(0.02)

        task = FakeOnetimeTask('Task', run)
        task._enabled = True
        self.executor.onetime_tasks = [task]
        with patch.object(task_executor_module.communicate.task, 'emit'), \
                patch.object(task_executor_module.communicate.notification, 'emit'), \
                patch.object(task_executor_module.communicate.executor_paused, 'emit'):
            self.executor.start()
            self.assertTrue(started.wait(WAIT))
            self.controls.start(lambda on_output: self.session.submit('"ran"', on_output=on_output))
            self.controls._update_status()

            self.assertEqual('Waiting for Task', self.controls.status_label.text())
            self.assertFalse(self.controls.stop_task_button.isHidden())

            self.controls.stop_current_task()
            self.assertTrue(self.process_until(lambda: self.results))

        self.assertFalse(task.enabled)
        self.assertEqual("'ran'", self.results[0].value)

    def test_busy_executor_shows_alert(self):
        with patch.object(task_executor_module.communicate.executor_exclusive, 'emit'):
            self.executor.acquire_exclusive('agent')

        with patch.object(job_controls_module, 'alert_error') as alert:
            job = self.controls.start(lambda on_output: self.session.submit('1', on_output=on_output))

        self.assertIsNone(job)
        self.assertIn('agent', alert.call_args.args[0])
        self.assertTrue(self.controls.run_button.isEnabled())


class DebugTabsTestCase(unittest.TestCase):
    """Builds the real tabs offscreen against a test executor."""

    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        import tempfile
        from ok import Config
        from ok.util.handler import ExitEvent
        capture = SimpleNamespace(connected=lambda: True,
                                  get_frame=lambda busy_wait=0: np.zeros((20, 20, 3), np.uint8))
        interaction = SimpleNamespace(should_capture=lambda: True, on_run=Mock(), on_destroy=Mock())
        self.executor = make_test_executor(capture, interaction)
        self.exit_event = ExitEvent()
        self.executor.exit_event = self.exit_event

        class Task:
            name = 'Task'

            def answer(self):
                print('thinking')
                return 42

        self.task = Task()
        self.executor.onetime_tasks = [self.task]
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        old_folder = Config.config_folder
        Config.config_folder = temp_dir.name
        self.addCleanup(setattr, Config, 'config_folder', old_folder)
        patches = [
            patch.object(task_executor_module, 'prevent_sleeping'),
            patch.object(og, 'executor', self.executor, create=True),
            patch.object(og, 'app', SimpleNamespace(tr=lambda message: message,
                                                    app=SimpleNamespace(aboutToQuit=SimpleNamespace(connect=Mock()))),
                         create=True),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.exit_event.set()
        self.executor.stop()
        if self.executor.thread is not None:
            self.executor.thread.join(WAIT)

    def process_until(self, condition):
        deadline = time.time() + WAIT
        while time.time() < deadline:
            QApplication.processEvents()
            if condition():
                return True
            time.sleep(0.01)
        return False

    def test_run_code_tab_runs_with_selected_task(self):
        from ok.ui.qt.debug.RunCodeTab import RunCodeTab
        tab = RunCodeTab({}, self.exit_event)
        self.addCleanup(delete, tab)
        tab.tasks_combo_box.setCurrentIndex(1)
        tab.code_input.setPlainText('print(task.name)\ntask.answer()')

        tab.run_code()

        self.assertTrue(self.process_until(lambda: '42' in tab.output_area.toPlainText()))
        self.assertEqual('Task\nthinking\n42\n', tab.output_area.toPlainText())
        self.assertEqual('Task', tab.config['target_task'])

    def test_debug_tab_call_shows_output_and_result(self):
        from ok.ui.qt.debug import DebugTab as debug_tab_module
        with patch.object(debug_tab_module, 'alert_info') as alert:
            tab = debug_tab_module.DebugTab({}, self.exit_event)
            self.addCleanup(delete, tab)
            tab.target_function_edit.setText('answer')

            tab.call()

            self.assertTrue(self.process_until(lambda: alert.called))
        self.assertEqual('thinking\n42', tab.result_edit.toPlainText())

    def test_debug_reload_button_queues_reload_and_reports_completion(self):
        from ok.ui.qt.debug import DebugTab as debug_tab_module
        from shiboken6 import delete

        entered, release = threading.Event(), threading.Event()
        def reload_tasks():
            def reload():
                entered.set()
                release.wait(WAIT)
                return [self.task]
            return self.executor.submit(reload)

        manager = SimpleNamespace(reload_tasks=Mock(side_effect=reload_tasks))
        with patch.object(og, 'task_manager', manager, create=True), \
                patch.object(debug_tab_module, 'alert_info') as alert:
            tab = debug_tab_module.DebugTab({}, self.exit_event)
            self.addCleanup(delete, tab)
            tab.reload_button.click()
            try:
                self.assertTrue(entered.wait(WAIT))
                self.assertFalse(tab.reload_button.isEnabled())
            finally:
                release.set()
            self.assertTrue(self.process_until(lambda: alert.called))
            manager.reload_tasks.assert_called_once_with()
            self.assertTrue(tab.reload_button.isEnabled())
            self.assertIn('1', alert.call_args.args[0])

    def test_run_code_selection_tracks_replaced_instances(self):
        from ok.core.events import communicate
        from ok.ui.qt.debug.RunCodeTab import RunCodeTab
        from shiboken6 import delete

        tab = RunCodeTab({}, self.exit_event)
        self.addCleanup(delete, tab)
        tab.tasks_combo_box.setCurrentIndex(1)
        tab.session.namespace['task'] = self.task
        replacement = type(self.task)()
        self.executor.onetime_tasks = [replacement]
        communicate.task_list_updated.emit()
        self.assertIs(tab.selected_task(), replacement)
        self.assertNotIn('task', tab.session.namespace)


if __name__ == '__main__':
    unittest.main()
