import unittest
from unittest.mock import Mock, patch

import ok.device.capture_methods.update as capture_update


class FakeClock:
    def __init__(self):
        self.value = 0

    def time(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class FakeCapture:
    def __init__(self, frames):
        self.frames = list(frames)

    def get_frame(self):
        if self.frames:
            return self.frames.pop(0)
        return None

    def get_name(self):
        return 'FakeCapture'


class TestCaptureUpdate(unittest.TestCase):
    def test_capture_can_produce_frame_retries_until_frame_arrives(self):
        clock = FakeClock()
        capture = FakeCapture([None, object()])

        with patch.object(capture_update.time, 'time', clock.time), \
                patch.object(capture_update.time, 'sleep', clock.sleep):
            self.assertTrue(capture_update._capture_can_produce_frame(capture, 1.0))

    def test_capture_can_produce_frame_times_out(self):
        clock = FakeClock()
        capture = FakeCapture([])

        with patch.object(capture_update.time, 'time', clock.time), \
                patch.object(capture_update.time, 'sleep', clock.sleep):
            self.assertFalse(capture_update._capture_can_produce_frame(capture, 0.1))

    def test_wgc_without_first_frame_is_closed_and_rejected(self):
        class FakeWGC:
            def __init__(self):
                self.last_start_failure_key = None
                self.last_start_failure_time = 0
                self.close = Mock()

            def start_or_stop(self):
                return True

            def get_capture_hwnd(self):
                return 123

            def get_frame(self):
                return None

            def get_name(self):
                return 'WGC'

        clock = FakeClock()
        fake_wgc = FakeWGC()

        with patch.object(capture_update, 'windows_graphics_available', return_value=True), \
                patch.object(capture_update, 'WindowsGraphicsCaptureMethod', FakeWGC), \
                patch.object(capture_update, 'get_capture', return_value=fake_wgc), \
                patch.object(capture_update.time, 'time', clock.time), \
                patch.object(capture_update.time, 'sleep', clock.sleep):
            self.assertIsNone(capture_update.get_win_graphics_capture(None, object(), object()))

        self.assertEqual(123, fake_wgc.last_start_failure_key)
        self.assertGreaterEqual(fake_wgc.last_start_failure_time, 0)
        fake_wgc.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
