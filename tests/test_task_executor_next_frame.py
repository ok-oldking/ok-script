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


if __name__ == '__main__':
    unittest.main()
