import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

from ok.device.capture_methods.base import BaseCaptureMethod
from ok.task.TaskExecutor import TaskExecutor
from ok.task.exceptions import CaptureBusyException


class LockedCapture(BaseCaptureMethod):
    """Reports BUSY while another caller owns the request lock, like WGC."""

    def __init__(self):
        super().__init__()
        self.exit_event = threading.Event()
        self.request_lock = threading.Lock()

    def do_get_frame(self):
        return self.do_get_frame_wait(0)

    def do_get_frame_wait(self, timeout):
        if timeout > 0:
            acquired = self.request_lock.acquire(timeout=timeout)
        else:
            acquired = self.request_lock.acquire(blocking=False)
        if not acquired:
            raise CaptureBusyException('busy')
        try:
            return np.zeros((20, 20, 3), np.uint8)
        finally:
            self.request_lock.release()


class TestNextFrameCaptureBusy(unittest.TestCase):
    def make_executor(self, method):
        executor = TaskExecutor.__new__(TaskExecutor)
        executor.lock = threading.Lock()
        executor.exit_event = threading.Event()
        executor.current_job = None
        executor.thread = None
        executor.blur_overlay_processor = None
        executor.device_manager = SimpleNamespace(capture_method=method)
        executor.reset_scene = lambda check_enabled=True: None
        executor.check_enabled = lambda check_pause=True: None
        executor.can_capture = lambda: True
        executor.sleep = Mock()
        return executor

    def test_waits_for_brief_one_off_capture_instead_of_sleeping(self):
        method = LockedCapture()
        executor = self.make_executor(method)
        method.request_lock.acquire()
        release = threading.Timer(.05, method.request_lock.release)
        release.start()

        frame = executor.next_frame()

        release.join(1)
        self.assertIsNotNone(frame)
        executor.sleep.assert_not_called()

    def test_busy_wait_does_not_exceed_time_out(self):
        method = LockedCapture()
        executor = self.make_executor(method)
        waits = []
        do_get_frame_wait = method.do_get_frame_wait
        method.do_get_frame_wait = lambda timeout: waits.append(timeout) or do_get_frame_wait(timeout)
        method.request_lock.acquire()
        try:
            frame = executor.next_frame(time_out=.03)
        finally:
            method.request_lock.release()

        self.assertIsNone(frame)
        self.assertGreater(min(waits), 0)
        self.assertLessEqual(max(waits), .03)


class TestResolutionFromFrame(unittest.TestCase):
    def make_executor(self):
        executor = TaskExecutor.__new__(TaskExecutor)
        executor.current_job = None
        executor.device_manager = SimpleNamespace(
            update_resolution_for_hwnd=Mock(),
            capture_method=Mock(width=0, height=0),
        )
        executor.device_manager.capture_method.get_frame.side_effect = AssertionError('Unexpected recapture')
        return executor

    def test_static_target_uses_valid_frame_without_recapture(self):
        executor = self.make_executor()
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        self.assertEqual((True, '1920x1080'), executor.check_frame_and_resolution(
            '16:9', (1280, 720), frame=frame))
        executor.device_manager.capture_method.get_frame.assert_not_called()

    def test_frame_below_minimum_is_still_rejected(self):
        executor = self.make_executor()
        frame = np.zeros((360, 640, 3), dtype=np.uint8)

        self.assertEqual((False, '640x360'), executor.check_frame_and_resolution(
            '16:9', (1280, 720), frame=frame))

    def test_capture_dimensions_override_stale_backend_dimensions(self):
        executor = self.make_executor()
        executor.device_manager.capture_method.get_frame.side_effect = None
        executor.device_manager.capture_method.get_frame.return_value = np.zeros((720, 1280, 3), dtype=np.uint8)

        self.assertEqual((True, '1280x720'), executor.check_frame_and_resolution('16:9', (1280, 720)))


if __name__ == '__main__':
    unittest.main()
