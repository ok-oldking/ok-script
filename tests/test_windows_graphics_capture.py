import unittest
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

import ok.device.capture_methods.windows_graphics as windows_graphics_module
from ok.device.capture_methods.browser import BrowserWindowAdapter
from ok.device.capture_methods.hwnd_window import HwndWindow
from ok.device.capture_methods.windows_graphics import WindowsGraphicsCaptureMethod
from ok.task.exceptions import CaptureBusyException


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


class _ObservedRLock:
    def __init__(self):
        self.lock = threading.RLock()
        self.attempted = threading.Event()

    def acquire(self, **kwargs):
        self.attempted.set()
        return self.lock.acquire(**kwargs)

    def release(self):
        self.lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_args):
        self.release()


class TestWindowsGraphicsCaptureLifecycle(unittest.TestCase):
    def _method(self):
        method = object.__new__(WindowsGraphicsCaptureMethod)
        method.lock = threading.RLock()
        method.get_frame_lock = _ObservedRLock()
        method.exit_event = threading.Event()
        method.frame_requested = threading.Event()
        method.frame_event = threading.Event()
        method._frame_cancel_generation = 0
        method._hwnd_window = SimpleNamespace(exists=True, capture_target_signature='new')
        method.get_capture_hwnd = lambda: 123
        method.capture_target_signature = 'old'
        method.frame_pool = Mock()
        method.session = None
        method.rtdevice = method.dxdevice = method.immediatedc = method.cputex = None
        method.contexts = {}
        method.last_start_failure_key = 123
        method.last_start_failure_time = time.time()
        return method

    def test_busy_target_change_is_deferred_without_holding_capture_lock(self):
        method = self._method()
        pool = method.frame_pool
        results = []
        errors = []

        def refresh():
            try:
                results.append(method.start_or_stop())
            except Exception as error:
                errors.append(error)

        # Simulate a frame consumer already owning the request lock while the
        # startup thread discovers a changed window target.
        with method.get_frame_lock:
            method.get_frame_lock.attempted.clear()
            worker = threading.Thread(target=refresh, daemon=True)
            worker.start()
            self.assertTrue(method.get_frame_lock.attempted.wait(1))
            acquired = method.lock.acquire(timeout=.2)
            if acquired:
                method.lock.release()
        worker.join(1)

        self.assertTrue(acquired, 'startup held the capture lock while waiting for a frame request')
        self.assertFalse(worker.is_alive())
        self.assertEqual([], results)
        self.assertEqual(1, len(errors))
        self.assertIsInstance(errors[0], CaptureBusyException)
        pool.Close.assert_not_called()
        self.assertIs(pool, method.frame_pool)

        # Once the request owner releases its lock, the refresh can safely
        # close the old target and retry the new one.
        self.assertFalse(method.start_or_stop())
        pool.Close.assert_called_once()
        self.assertIsNone(method.frame_pool)

    def test_busy_capture_reports_retryable_busy_without_entering_capture(self):
        for operation in ('start_or_stop', 'do_get_frame'):
            with self.subTest(operation=operation):
                method = self._method()
                method._start_or_stop = Mock()
                method._do_get_frame = Mock()
                errors = []

                def call():
                    try:
                        getattr(method, operation)()
                    except Exception as error:
                        errors.append(error)

                with method.get_frame_lock, patch.object(windows_graphics_module, 'WGC_FRAME_WAIT_TIMEOUT', .05):
                    worker = threading.Thread(target=call, daemon=True)
                    worker.start()
                    worker.join(.5)
                    self.assertFalse(worker.is_alive())
                self.assertEqual(1, len(errors))
                self.assertIsInstance(errors[0], CaptureBusyException)
                self.assertIn('Windows Graphics Capture is busy', str(errors[0]))
                method._start_or_stop.assert_not_called()
                method._do_get_frame.assert_not_called()

    def test_busy_frame_probe_propagates_busy_without_entering_capture(self):
        method = self._method()
        method._do_get_frame = Mock()
        errors = []

        def probe():
            try:
                method.get_frame_for_probe(.01)
            except Exception as error:
                errors.append(error)

        with method.get_frame_lock:
            worker = threading.Thread(target=probe, daemon=True)
            worker.start()
            worker.join(.5)
            self.assertFalse(worker.is_alive())

        self.assertEqual(1, len(errors))
        self.assertIsInstance(errors[0], CaptureBusyException)
        method._do_get_frame.assert_not_called()

    def test_busy_window_setter_defers_refresh(self):
        method = self._method()
        method.start_or_stop = Mock(side_effect=CaptureBusyException('busy'))
        window = object()

        method.hwnd_window = window

        self.assertIs(window, method.hwnd_window)
        method.start_or_stop.assert_called_once()

    def test_frame_request_can_restart_changed_target_without_deadlocking_itself(self):
        method = self._method()
        pool = method.frame_pool

        self.assertIsNone(method.do_get_frame())

        pool.Close.assert_called_once()
        self.assertIsNone(method.frame_pool)


class TestCaptureTargetSignature(unittest.TestCase):
    def test_capture_origin_uses_fallback_crop_for_embedded_title_bar(self):
        window = object.__new__(HwndWindow)
        window.x = 100
        window.y = 200
        window.window_width = 1920
        window.window_height = 1140
        window.client_width = 1920
        window.client_height = 1140
        window.width = 1920
        window.height = 1080
        window.real_x_offset = 0
        window.real_y_offset = 0

        self.assertEqual((100, 260), window.get_capture_origin())

    def test_capture_origin_prefers_discovered_render_surface_offset(self):
        window = object.__new__(HwndWindow)
        window.x = 100
        window.y = 200
        window.window_width = 1920
        window.window_height = 1140
        window.client_width = 1920
        window.client_height = 1140
        window.width = 1920
        window.height = 1080
        window.real_x_offset = 8
        window.real_y_offset = 42

        self.assertEqual((108, 242), window.get_capture_origin())

    def test_capture_origin_does_not_double_count_standard_window_decorations(self):
        window = object.__new__(HwndWindow)
        # x/y are already the client area's screen origin. The larger outer
        # dimensions include the standard Windows border and title bar.
        window.x = 108
        window.y = 242
        window.window_width = 1296
        window.window_height = 759
        window.client_width = 1280
        window.client_height = 720
        window.width = 1280
        window.height = 720
        window.real_x_offset = 0
        window.real_y_offset = 0

        self.assertEqual((108, 242), window.get_capture_origin())

    def test_hwnd_window_signature_tracks_hwnd_tree_and_geometry(self):
        window = object.__new__(HwndWindow)
        window.hwnd = 10
        window.top_hwnd = 11
        window.width = 1280
        window.height = 720
        window.client_width = 1280
        window.client_height = 752
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
        method._frame_cancel_generation = 0
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
        method._frame_cancel_generation = 0
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

        with patch.object(windows_graphics_module.time, 'monotonic', side_effect=[0.0, 5.0]):
            result = method.do_get_frame()

        self.assertIsNone(result)
        self.assertFalse(method.frame_requested.is_set())
        self.assertIsNone(method.last_frame)

    def test_probe_uses_outer_deadline_after_waiting_for_request_lock(self):
        method = self._method(_FakeFrame())
        method.get_frame_lock = Mock()
        method.get_frame_lock.acquire.return_value = True
        method.frame_event.wait = Mock()

        # The lock consumes 0.1s of the 0.25s budget. The frame loop must
        # still expire at 10.25, rather than starting a new four-second wait.
        with patch.object(windows_graphics_module.time, 'monotonic',
                          side_effect=[10.0, 10.1, 10.25]):
            result = method.get_frame_for_probe(.25)

        self.assertIsNone(result)
        method.get_frame_lock.acquire.assert_called_once_with(timeout=.25)
        method.get_frame_lock.release.assert_called_once()
        method.frame_event.wait.assert_called_once_with(.05)
        self.assertFalse(method.frame_requested.is_set())

    def test_exit_event_interrupts_pending_frame_wait(self):
        method = self._method(_FakeFrame())
        method.last_frame = None
        result = []
        worker = threading.Thread(target=lambda: result.append(method.do_get_frame()))
        worker.start()
        self.assertTrue(method.frame_requested.wait(1))

        method.exit_event.set()
        worker.join(.3)

        self.assertFalse(worker.is_alive())
        self.assertEqual([None], result)
        self.assertFalse(method.frame_requested.is_set())

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

        results = []
        with patch.object(windows_graphics_module, 'composite_hwnds', side_effect=lambda captured, *_: captured):
            consumer = threading.Thread(target=lambda: results.append(method.do_get_frame()))
            consumer.start()
            self.assertTrue(method.frame_requested.wait(1))

            # Normal consumers retry when busy without cancelling or consuming
            # the request already owned by the first caller.
            self.assertIsNone(method.get_frame())
            self.assertTrue(method.frame_requested.is_set())
            method.frame_arrived_callback()
            consumer.join(1)
            self.assertFalse(consumer.is_alive())

            producer = threading.Thread(target=lambda: (
                method.frame_requested.wait(1) and method.frame_arrived_callback()))
            producer.start()
            results.append(method.do_get_frame())
            producer.join(1)

        self.assertFalse(producer.is_alive())
        self.assertEqual([2, 3], [int(result[0, 0, 0]) for result in results])

if __name__ == '__main__':
    unittest.main()
