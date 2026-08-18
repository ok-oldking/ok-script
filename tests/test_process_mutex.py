import os
import threading
import unittest
from unittest.mock import Mock, patch

from ok.util import process
from ok.util.process import _process_matches_app


class TestProcessMutexMatching(unittest.TestCase):
    def make_process(self, pid=123, exe='C:/app/python.exe', cwd='C:/app',
                     cmdline=None):
        process = Mock(pid=pid)
        process.exe.return_value = exe
        process.cwd.return_value = cwd
        process.cmdline.return_value = cmdline or [exe, 'main.py']
        return process

    @patch('ok.util.process.os.getppid', return_value=2)
    @patch('ok.util.process.os.getpid', return_value=1)
    def test_matches_complete_application_signature(self, _pid, _ppid):
        process = self.make_process()
        self.assertTrue(_process_matches_app(
            process,
            os.path.normcase(os.path.realpath('C:/app/python.exe')),
            os.path.normcase(os.path.realpath('C:/app')),
            os.path.normcase(os.path.realpath('C:/app/main.py')),
        ))

    @patch('ok.util.process.os.getppid', return_value=2)
    @patch('ok.util.process.os.getpid', return_value=1)
    def test_rejects_unrelated_script_using_same_python(self, _pid, _ppid):
        process = self.make_process(cmdline=['C:/app/python.exe', 'worker.py'])
        self.assertFalse(_process_matches_app(
            process,
            os.path.normcase(os.path.realpath('C:/app/python.exe')),
            os.path.normcase(os.path.realpath('C:/app')),
            os.path.normcase(os.path.realpath('C:/app/main.py')),
        ))


class TestExitWatchdog(unittest.TestCase):
    def setUp(self):
        process._exit_watchdog_started = False

    def tearDown(self):
        process._exit_watchdog_started = False

    @patch('ok.util.process._write_shutdown_thread_dump', return_value='dump.txt')
    def test_forces_exit_after_grace_period(self, _dump):
        forced = threading.Event()
        codes = []

        watchdog = process.start_exit_watchdog(
            grace_period=0, exit_code=7,
            force_exit=lambda code: (codes.append(code), forced.set()))

        self.assertTrue(watchdog.daemon)
        self.assertTrue(forced.wait(1))
        watchdog.join(1)
        self.assertEqual([7], codes)

    @patch('ok.util.process._write_shutdown_thread_dump', return_value='dump.txt')
    def test_only_starts_once(self, _dump):
        release = threading.Event()
        first = process.start_exit_watchdog(
            grace_period=0, force_exit=lambda _code: release.set())
        second = process.start_exit_watchdog(
            grace_period=0, force_exit=lambda _code: None)

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertTrue(release.wait(1))
        first.join(1)


if __name__ == '__main__':
    unittest.main()
