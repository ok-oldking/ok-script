import threading
import time
import unittest

from ok.task.TaskExecutor import TaskExecutor
from ok.task.exceptions import CaptureException


class TestFrameStall(unittest.TestCase):
    def make_executor(self):
        executor = TaskExecutor.__new__(TaskExecutor)
        executor.exit_event = threading.Event()
        executor.paused = False
        executor.debug_mode = False
        executor._frame = None
        executor.frame_stall_timeout = 0.1
        return executor

    def test_frame_raises_capture_exception_when_capture_stalls(self):
        executor = self.make_executor()

        def stalled_next_frame(time_out=6):
            time.sleep(0.02)
            return None

        executor.next_frame = stalled_next_frame
        with self.assertRaises(CaptureException):
            _ = executor.frame

    def test_frame_returns_frame_when_capture_recovers(self):
        executor = self.make_executor()
        calls = []

        def recovering_next_frame(time_out=6):
            calls.append(1)
            if len(calls) >= 2:
                executor._frame = 'frame'
            return executor._frame

        executor.next_frame = recovering_next_frame
        self.assertEqual('frame', executor.frame)
        self.assertGreaterEqual(len(calls), 2)

    def test_frame_returns_existing_frame_without_capture(self):
        executor = self.make_executor()
        executor._frame = 'frame'
        self.assertEqual('frame', executor.frame)


if __name__ == '__main__':
    unittest.main()
