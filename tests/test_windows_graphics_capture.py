import unittest
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import ok.device.capture_methods.windows_graphics as windows_graphics_module
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
        method.get_frame_lock = threading.Lock()
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


class TestWindowsGraphicsCaptureGetFrame(unittest.TestCase):
    def _method(self, frame):
        method = object.__new__(WindowsGraphicsCaptureMethod)
        method.lock = threading.RLock()
        method.get_frame_lock = threading.Lock()
        method.exit_event = threading.Event()
        method.frame_event = threading.Event()
        method.frame_requested = threading.Event()
        method.frame_pool = _FakeFramePool(frame)
        method.last_frame = np.full((2, 2, 3), 1, dtype=np.uint8)
        method.last_frame_time = time.time()
        method.start_or_stop = lambda: True
        method.crop_image = lambda captured: captured
        method.hwnd_window = None
        method.contexts = []
        return method

    def test_get_frame_discards_cached_frame_and_waits_for_fresh_request(self):
        source_frame = _FakeFrame()
        method = self._method(source_frame)
        fresh = np.full((2, 2, 3), 2, dtype=np.uint8)
        method.convert_dx_frame = lambda _frame: fresh
        callback_ran = threading.Event()

        def deliver_requested_frame():
            if method.frame_requested.wait(1):
                method.frame_arrived_callback()
                callback_ran.set()

        producer = threading.Thread(target=deliver_requested_frame)
        producer.start()
        with patch.object(windows_graphics_module, 'composite_hwnds', side_effect=lambda captured, *_: captured):
            result = method.do_get_frame()
        producer.join(1)

        self.assertTrue(callback_ran.is_set())
        np.testing.assert_array_equal(fresh, result)
        self.assertTrue(source_frame.closed)

    def test_timeout_cancels_request_without_caching_a_frame(self):
        method = self._method(_FakeFrame())
        method.last_frame = None

        with patch.object(windows_graphics_module.time, 'monotonic', side_effect=[0.0, 2.0]):
            result = method.do_get_frame()

        self.assertIsNone(result)
        self.assertFalse(method.frame_requested.is_set())
        self.assertIsNone(method.last_frame)

    def test_repeated_requests_continue_receiving_new_frames(self):
        method = self._method(_FakeFrame())
        values = iter(range(2, 22))
        method.convert_dx_frame = lambda _frame: np.full((2, 2, 3), next(values), dtype=np.uint8)

        def deliver_frames():
            for _ in range(20):
                if not method.frame_requested.wait(1):
                    return
                method.frame_arrived_callback()

        producer = threading.Thread(target=deliver_frames)
        producer.start()
        results = []
        with patch.object(windows_graphics_module, 'composite_hwnds', side_effect=lambda captured, *_: captured):
            for _ in range(20):
                results.append(int(method.do_get_frame()[0, 0, 0]))
        producer.join(1)

        self.assertFalse(producer.is_alive())
        self.assertEqual(list(range(2, 22)), results)

    def test_concurrent_callers_do_not_consume_each_others_frame(self):
        method = self._method(_FakeFrame())
        values = iter((2, 3))
        method.convert_dx_frame = lambda _frame: np.full((2, 2, 3), next(values), dtype=np.uint8)

        def deliver_frames():
            for _ in range(2):
                if not method.frame_requested.wait(1):
                    return
                method.frame_arrived_callback()

        producer = threading.Thread(target=deliver_frames)
        producer.start()
        results = []
        with patch.object(windows_graphics_module, 'composite_hwnds', side_effect=lambda captured, *_: captured):
            consumers = [threading.Thread(target=lambda: results.append(method.do_get_frame())) for _ in range(2)]
            for consumer in consumers:
                consumer.start()
            for consumer in consumers:
                consumer.join(2)
        producer.join(1)

        self.assertTrue(all(not consumer.is_alive() for consumer in consumers))
        self.assertFalse(producer.is_alive())
        self.assertEqual([2, 3], sorted(int(result[0, 0, 0]) for result in results))

if __name__ == '__main__':
    unittest.main()
