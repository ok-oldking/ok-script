import os
import json
from pathlib import Path
import tempfile
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

    def test_virtual_environment_redirector_matches_its_command_line_interpreter(self):
        proc = self.make_process(exe='C:/Python/python.exe',
                                 cmdline=['C:/app/.venv/Scripts/python.exe', 'main.py'])
        self.assertTrue(_process_matches_app(
            proc, process._normalized_path('C:/app/.venv/Scripts/python.exe'),
            process._normalized_path('C:/app'), process._normalized_path('C:/app/main.py')))


class TestGuiConsoleHandoff(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.marker = str(Path(self.directory.name) / 'owner.pid')
        self.owner = Mock(pid=123)
        self.owner.exe.return_value = 'C:/Python/python.exe'
        self.owner.cwd.return_value = 'C:/app'
        self.owner.cmdline.return_value = ['C:/env/Scripts/python.exe', 'start_mcp.py']
        self.owner.create_time.return_value = 1234.5
        self.signature = (process._normalized_path('C:/env/Scripts/pythonw.exe'),
                          process._normalized_path('C:/app'),
                          process._normalized_path('C:/app/start_gui.py'))
        self.write_owner()

    def write_owner(self, **updates):
        record = {'pid': 123, 'create_time': 1234.5, 'mode': 'console'}
        record.update(updates)
        Path(self.marker).write_text(json.dumps(record), encoding='ascii')

    def find(self, replace_console=True):
        with patch.object(process, '_current_app_signature', return_value=self.signature), \
                patch.object(process.psutil, 'Process', return_value=self.owner), \
                patch.object(process.psutil, 'process_iter', return_value=[]) as scan:
            result = process._find_previous_instances(self.marker, replace_console=replace_console)
            if replace_console:
                scan.assert_not_called()
            return result

    def test_gui_replaces_recorded_console_with_different_entry_script(self):
        self.assertEqual([self.owner], self.find())

    def test_default_matching_does_not_widen_to_different_entry_scripts(self):
        self.assertEqual([], self.find(replace_console=False))

    def test_gui_does_not_kill_another_project(self):
        self.owner.cwd.return_value = 'C:/other-project'
        self.assertEqual([], self.find())

    def test_gui_does_not_kill_another_virtual_environment(self):
        self.owner.cmdline.return_value = ['C:/other-env/python.exe', 'start_mcp.py']
        self.assertEqual([], self.find())

    def test_redirector_with_base_binary_in_both_exe_and_argv(self):
        self.write_owner(executable='C:/env/Scripts/python.exe')
        self.owner.cmdline.return_value = ['C:/Python/python.exe', 'start_mcp.py']
        with patch.object(process.sys, '_base_executable', 'C:/Python/pythonw.exe'):
            self.assertEqual([self.owner], self.find())

    def test_recorded_environment_must_match_even_when_base_python_is_shared(self):
        self.write_owner(executable='C:/other-env/Scripts/python.exe')
        self.owner.cmdline.return_value = ['C:/Python/python.exe', 'start_mcp.py']
        with patch.object(process.sys, '_base_executable', 'C:/Python/pythonw.exe'):
            self.assertEqual([], self.find())

    def test_duplicate_gui_still_matches_the_same_script_through_a_redirector(self):
        self.write_owner(mode='gui', executable='C:/env/Scripts/pythonw.exe')
        self.owner.exe.return_value = 'C:/Python/pythonw.exe'
        self.owner.cmdline.return_value = ['C:/Python/pythonw.exe', 'start_gui.py']
        with patch.object(process.sys, '_base_executable', 'C:/Python/pythonw.exe'):
            self.assertEqual([self.owner], self.find(replace_console=False))

    def test_gui_does_not_treat_a_recorded_gui_as_console(self):
        self.write_owner(mode='gui')
        self.assertEqual([], self.find())

    def test_reused_owner_pid_is_rejected(self):
        self.owner.create_time.return_value = 2000.0
        self.assertEqual([], self.find())

    def test_legacy_console_pid_marker_is_supported(self):
        Path(self.marker).write_text('123', encoding='ascii')
        self.assertEqual([self.owner], self.find())
        self.assertEqual(123, process._read_owner_pid(self.marker))

    def test_legacy_pid_marker_with_a_virtual_environment_redirector(self):
        Path(self.marker).write_text('123', encoding='ascii')
        self.owner.cmdline.return_value = ['C:/Python/python.exe', 'start_mcp.py']
        with patch.object(process.sys, '_base_executable', 'C:/Python/pythonw.exe'):
            self.assertEqual([self.owner], self.find())

    def test_missing_marker_does_not_scan_and_kill_python_jobs(self):
        Path(self.marker).unlink()
        self.assertEqual([], self.find())

    def test_only_the_verified_console_owner_is_killed(self):
        with patch.object(process, '_current_app_signature', return_value=self.signature), \
                patch.object(process.psutil, 'Process', return_value=self.owner), \
                patch.object(process.psutil, 'process_iter') as scan:
            self.assertTrue(process._terminate_previous_instances(self.marker, replace_console=True))
        self.owner.kill.assert_called_once_with()
        scan.assert_not_called()


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
