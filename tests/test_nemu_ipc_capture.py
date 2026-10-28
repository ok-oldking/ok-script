import threading
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, mock_open, patch

from ok.device.capture_methods.nemu_ipc import NemuIpcCaptureMethod
from ok.capture.adb.nemu_ipc import NemuIpcImpl
from ok.util.window import get_player_id_from_cmdline


class TestNemuIpcCaptureMethod(unittest.TestCase):
    def make_capture(self):
        device_manager = SimpleNamespace()
        capture = NemuIpcCaptureMethod(device_manager, threading.Event())
        capture.emulator = SimpleNamespace(path=r'C:\MuMu\shell\MuMuPlayer.exe', player_id=0)
        return capture

    def test_initialized_capture_reuses_connection_without_rechecking_config(self):
        capture = self.make_capture()
        capture.nemu_impl = SimpleNamespace(screenshot=Mock(return_value='frame'))
        capture.check_mumu_app_keep_alive_400 = Mock()

        self.assertEqual('frame', capture.do_get_frame())
        self.assertEqual('frame', capture.do_get_frame())

        capture.check_mumu_app_keep_alive_400.assert_not_called()
        self.assertEqual(2, capture.nemu_impl.screenshot.call_count)

    def test_first_capture_initializes_then_uses_screenshot(self):
        capture = self.make_capture()
        implementation = SimpleNamespace(screenshot=Mock(return_value='frame'))
        capture.check_mumu_app_keep_alive_400 = Mock()

        with patch('ok.capture.adb.nemu_ipc.NemuIpc', return_value=implementation):
            self.assertEqual('frame', capture.do_get_frame())

        capture.check_mumu_app_keep_alive_400.assert_called_once_with()
        implementation.screenshot.assert_called_once_with(timeout=0.5)

    def test_legacy_mumu_loads_sdk_from_shell(self):
        root = os.path.abspath('MuMu')
        expected = os.path.join(root, 'shell', 'sdk', 'external_renderer_ipc.dll')
        with patch('ok.capture.adb.nemu_ipc.os.path.exists', side_effect=lambda path: path == expected), \
                patch('ok.capture.adb.nemu_ipc.ctypes.CDLL') as load:
            NemuIpcImpl(root, 0)
        load.assert_called_once_with(expected)

    def test_mumu_15_capture_passes_selected_runtime_version(self):
        capture = self.make_capture()
        capture.emulator.name = 'MuMuPlayer-15.0-0'
        capture.check_mumu_app_keep_alive_400 = Mock()
        with patch('ok.capture.adb.nemu_ipc.NemuIpc') as implementation:
            capture.init_nemu()
        implementation.assert_called_once_with(
            nemu_folder=capture.base_folder(), instance_id=0,
            display_id=0, runtime_version='15.0')

    def test_mumu_15_loads_sdk_from_selected_runtime(self):
        root = os.path.abspath('MuMu')
        expected = os.path.join(root, 'nx_device', '15.0', 'shell', 'sdk', 'external_renderer_ipc.dll')
        with patch('ok.capture.adb.nemu_ipc.os.path.exists', side_effect=lambda path: path == expected), \
                patch('ok.capture.adb.nemu_ipc.ctypes.CDLL') as load:
            NemuIpcImpl(root, 0, runtime_version='15.0')
        load.assert_called_once_with(expected)

    def test_keep_alive_check_uses_actual_instance_name(self):
        capture = self.make_capture()
        capture.emulator.name = 'MuMuPlayer-15.0-0'
        file = mock_open(read_data='{"customer": {"app_keptlive": "true"}}')
        with patch('builtins.open', file), self.assertRaisesRegex(Exception, 'background keep alive'):
            capture.check_mumu_app_keep_alive_400()
        file.assert_called_once_with(os.path.join(
            capture.base_folder(), 'vms', 'MuMuPlayer-15.0-0', 'configs', 'customer_config.json'),
            mode='r', encoding='utf-8')

    def test_mumu_restart_pid_does_not_override_instance_index(self):
        self.assertEqual(0, get_player_id_from_cmdline([
            'MuMuNxDevice.exe', '-r', 'true', '--restart-last-pid', '55708',
            '-v', '0', '--vm', 'MuMuPlayer-15.0-0']))


if __name__ == '__main__':
    unittest.main()
