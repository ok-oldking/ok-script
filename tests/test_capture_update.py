import unittest
from unittest.mock import Mock, patch

import ok.device.capture_methods.update as capture_update
from ok.task.exceptions import CaptureBusyException


class FakeClock:
    def __init__(self):
        self.value = 0

    def time(self):
        return self.value

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class FakeCapture:
    def __init__(self, frames):
        self.frames = list(frames)

    def get_frame_for_probe(self, timeout):
        if self.frames:
            return self.frames.pop(0)
        return None

    def get_name(self):
        return 'FakeCapture'


class TestCaptureUpdate(unittest.TestCase):
    def test_capture_can_produce_frame_retries_until_frame_arrives(self):
        clock = FakeClock()
        capture = FakeCapture([None, object()])

        with patch.object(capture_update.time, 'monotonic', clock.monotonic), \
                patch.object(capture_update.time, 'sleep', clock.sleep):
            self.assertTrue(capture_update._capture_can_produce_frame(capture, 1.0))

    def test_capture_can_produce_frame_times_out(self):
        clock = FakeClock()
        capture = FakeCapture([])

        with patch.object(capture_update.time, 'monotonic', clock.monotonic), \
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

            def get_frame_for_probe(self, timeout):
                return None

            def get_name(self):
                return 'WGC'

        clock = FakeClock()
        fake_wgc = FakeWGC()

        with patch.object(capture_update, 'windows_graphics_available', return_value=True), \
                patch.object(capture_update, 'WindowsGraphicsCaptureMethod', FakeWGC), \
                patch.object(capture_update, 'get_capture', return_value=fake_wgc), \
                patch.object(capture_update.time, 'time', clock.time), \
                patch.object(capture_update.time, 'monotonic', clock.monotonic), \
                patch.object(capture_update.time, 'sleep', clock.sleep):
            self.assertIsNone(capture_update.get_win_graphics_capture(None, object(), object()))

        self.assertEqual(123, fake_wgc.last_start_failure_key)
        self.assertGreaterEqual(fake_wgc.last_start_failure_time, 0)
        fake_wgc.close.assert_called_once()

    def test_busy_capture_probe_propagates_busy(self):
        capture = FakeCapture([])
        capture.get_frame_for_probe = Mock(side_effect=CaptureBusyException('busy'))

        with self.assertRaises(CaptureBusyException):
            capture_update._capture_can_produce_frame(capture, 1.0)

    def test_capture_probe_passes_remaining_budget(self):
        clock = FakeClock()
        capture = FakeCapture([None, object()])
        capture.get_frame_for_probe = Mock(wraps=capture.get_frame_for_probe)

        with patch.object(capture_update.time, 'monotonic', clock.monotonic), \
                patch.object(capture_update.time, 'sleep', clock.sleep):
            self.assertTrue(capture_update._capture_can_produce_frame(capture, 0.1))

        self.assertEqual([unittest.mock.call(0.1), unittest.mock.call(0.05)],
                         capture.get_frame_for_probe.call_args_list)

    def test_busy_wgc_stays_selected_without_fallback_or_failure_cache(self):
        for busy_operation in ('start_or_stop', 'get_frame_for_probe'):
            with self.subTest(busy_operation=busy_operation):
                capture = Mock(spec=capture_update.WindowsGraphicsCaptureMethod)
                capture.last_start_failure_key = None
                capture.last_start_failure_time = 0
                capture.start_or_stop.return_value = True
                getattr(capture, busy_operation).side_effect = CaptureBusyException('busy')
                fallback = Mock()

                def get_capture(existing, target, hwnd, exit_event):
                    if target is capture_update.WindowsGraphicsCaptureMethod:
                        return capture
                    return fallback

                with patch.object(capture_update, 'windows_graphics_available', return_value=True), \
                        patch.object(capture_update, 'get_capture', side_effect=get_capture) as select:
                    result = capture_update.update_capture_method(
                        {'capture_method': ['WGC', 'BitBlt']}, capture, object())

                self.assertIs(capture, result)
                self.assertEqual(1, select.call_count)
                capture.close.assert_not_called()
                self.assertIsNone(capture.last_start_failure_key)
                self.assertEqual(0, capture.last_start_failure_time)

    def test_failed_wgc_start_is_cached_closed_and_falls_back(self):
        capture = Mock(spec=capture_update.WindowsGraphicsCaptureMethod)
        capture.start_or_stop.return_value = False
        capture.get_capture_hwnd.return_value = 123
        fallback = object()

        with patch.object(capture_update, 'windows_graphics_available', return_value=True), \
                patch.object(capture_update, 'get_capture', side_effect=[capture, fallback]):
            result = capture_update.update_capture_method(
                {'capture_method': ['WGC', 'BitBlt']}, capture, object())

        self.assertIs(fallback, result)
        self.assertEqual(123, capture.last_start_failure_key)
        capture.close.assert_called_once()
        capture.get_frame_for_probe.assert_not_called()


if __name__ == '__main__':
    unittest.main()
