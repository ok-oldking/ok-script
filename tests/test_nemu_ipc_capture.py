import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ok.device.capture_methods.nemu_ipc import NemuIpcCaptureMethod


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


if __name__ == '__main__':
    unittest.main()
