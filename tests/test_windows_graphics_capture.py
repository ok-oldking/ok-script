import unittest
import threading
from types import SimpleNamespace

from ok.device.capture_methods.browser import BrowserWindowAdapter
from ok.device.capture_methods.hwnd_window import HwndWindow
from ok.device.capture_methods.windows_graphics import WindowsGraphicsCaptureMethod


class _FakeFrame:
    def __init__(self):
        self.closed = False

    def Close(self):
        self.closed = True


class _FakeFramePool:
    def __init__(self, frame):
        self.frame = frame

    def TryGetNextFrame(self):
        return self.frame


class TestCaptureTargetSignature(unittest.TestCase):
    def test_hwnd_window_signature_tracks_hwnd_tree_and_geometry(self):
        window = object.__new__(HwndWindow)
        window.hwnd = 10
        window.top_hwnd = 11
        window.width = 1280
        window.height = 720
        window.real_x_offset = 0
        window.real_y_offset = 32
        window.real_width = 1280
        window.real_height = 720
        window.hwnds = [(10,), (11,)]

        original = window.capture_target_signature

        window.hwnds = [(10,), (12,)]
        self.assertNotEqual(original, window.capture_target_signature)

        window.hwnds = [(10,), (11,)]
        window.real_y_offset = 0
        self.assertNotEqual(original, window.capture_target_signature)

    def test_browser_window_adapter_exposes_capture_target_signature(self):
        browser_capture = SimpleNamespace(
            hwnd=10,
            top_hwnd=11,
            width=1280,
            height=720,
            x_offset=0,
            y_offset=32,
            exe_full_path='browser.exe',
        )
        adapter = BrowserWindowAdapter(browser_capture)

        self.assertEqual((10, 1280, 720, 0, 32, 'browser.exe'), adapter.capture_target_signature)


class TestWindowsGraphicsCaptureCallback(unittest.TestCase):
    def _method_with_frame(self, frame):
        method = object.__new__(WindowsGraphicsCaptureMethod)
        method.lock = threading.RLock()
        method.exit_event = threading.Event()
        method.frame_event = threading.Event()
        method.frame_requested = threading.Event()
        method.frame_requested.set()
        method.frame_pool = _FakeFramePool(frame)
        method.last_frame = None
        method.last_frame_time = 0
        return method

    def test_frame_arrived_converts_while_locked_and_closes_frame(self):
        frame = _FakeFrame()
        method = self._method_with_frame(frame)
        lock_state = {}

        def convert_dx_frame(next_frame):
            lock_state['owned_during_convert'] = method.lock._is_owned()
            self.assertIs(next_frame, frame)
            return 'converted'

        method.convert_dx_frame = convert_dx_frame

        method.frame_arrived_callback()

        self.assertTrue(lock_state['owned_during_convert'])
        self.assertEqual('converted', method.last_frame)
        self.assertTrue(method.frame_event.is_set())
        self.assertTrue(frame.closed)

    def test_frame_arrived_skips_cpu_conversion_without_pending_request(self):
        frame = _FakeFrame()
        method = self._method_with_frame(frame)
        method.frame_requested.clear()
        converted = []
        method.convert_dx_frame = lambda next_frame: converted.append(next_frame)

        method.frame_arrived_callback()

        self.assertEqual([], converted)
        self.assertIsNone(method.last_frame)
        self.assertFalse(method.frame_event.is_set())
        self.assertTrue(frame.closed)

    def test_frame_arrived_closes_frame_when_convert_fails(self):
        frame = _FakeFrame()
        method = self._method_with_frame(frame)

        def convert_dx_frame(_next_frame):
            raise RuntimeError('convert failed')

        method.convert_dx_frame = convert_dx_frame

        method.frame_arrived_callback()

        self.assertIsNone(method.last_frame)
        self.assertFalse(method.frame_event.is_set())
        self.assertTrue(frame.closed)


if __name__ == '__main__':
    unittest.main()
