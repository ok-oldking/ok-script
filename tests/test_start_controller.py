import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import ok.gui.StartController as start_controller_module
from ok.gui.StartController import StartController
from ok.util.gpu_driver_settings import GpuDriverPostProcessing


class FakeClock:
    def __init__(self):
        self.value = 0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class FakeWindow:
    def __init__(self, sizes):
        self.sizes = iter(sizes)
        self.hwnd = 0
        self.width = 0
        self.height = 0
        self.updates = 0

    def do_update_window_size(self):
        self.width, self.height = next(self.sizes)
        self.hwnd = 1
        self.updates += 1


class TestStartController(unittest.TestCase):
    def make_controller(self):
        controller = StartController.__new__(StartController)
        controller.exit_event = threading.Event()
        controller.start_timeout = 20
        controller.STARTED_WINDOW_STABLE_SECONDS = 2
        controller.STARTED_WINDOW_POLL_INTERVAL = 1
        return controller

    def test_started_window_must_be_usable_and_stable_before_continuing(self):
        controller = self.make_controller()
        window = FakeWindow([(80, 80), (120, 120), (140, 120), (140, 120), (140, 120)])
        clock = FakeClock()
        fake_og = SimpleNamespace(device_manager=SimpleNamespace(hwnd_window=window))

        with patch.object(start_controller_module, 'og', fake_og), \
                patch.object(start_controller_module.time, 'monotonic', clock.monotonic), \
                patch.object(start_controller_module.time, 'sleep', clock.sleep):
            self.assertTrue(controller._wait_until_started_window_stable())

        self.assertEqual(5, window.updates)

    def test_started_window_wait_does_not_restart_countdown(self):
        controller = self.make_controller()
        controller.STARTED_WINDOW_STABLE_SECONDS = 1
        controller.STARTED_WINDOW_POLL_INTERVAL = 0.2
        window = FakeWindow([(120, 120)] * 6)
        clock = FakeClock()
        fake_og = SimpleNamespace(device_manager=SimpleNamespace(hwnd_window=window))
        emit = Mock()
        fake_communicate = SimpleNamespace(starting_emulator=SimpleNamespace(emit=emit))

        with patch.object(start_controller_module, 'og', fake_og), \
                patch.object(start_controller_module, 'communicate', fake_communicate), \
                patch.object(start_controller_module.time, 'monotonic', clock.monotonic), \
                patch.object(start_controller_module.time, 'sleep', clock.sleep):
            self.assertTrue(controller._wait_until_started_window_stable())

        emit.assert_not_called()

    def test_started_windows_wait_for_stability_before_capture_readiness(self):
        controller = self.make_controller()
        device_manager = Mock()
        device_manager.get_preferred_device.return_value = {
            'connected': False,
            'device': 'windows',
        }
        device_manager.get_exe_path.return_value = r'C:\game.exe'
        fake_og = SimpleNamespace(
            device_manager=device_manager,
            global_config=Mock(),
        )
        fake_og.global_config.get_config.return_value = None

        call_order = []
        controller._wait_until_started_window_stable = Mock(
            side_effect=lambda: call_order.append('stable') or True)
        controller._wait_until_device_ready = Mock(
            side_effect=lambda: call_order.append('ready') or True)

        with patch.object(start_controller_module, 'og', fake_og), \
                patch.object(start_controller_module, 'is_admin', return_value=True), \
                patch.object(start_controller_module, 'execute',
                             side_effect=lambda *args, **kwargs: call_order.append('execute') or True):
            self.assertTrue(controller.start_device())

        self.assertEqual(['execute', 'stable', 'ready'], call_order)

    def test_gpu_driver_warning_identifies_each_enabled_vendor_feature(self):
        controller = self.make_controller()
        emit = Mock()
        fake_communicate = SimpleNamespace(notification=SimpleNamespace(emit=emit))
        enabled_features = [
            GpuDriverPostProcessing("NVIDIA", "RTX HDR", True),
            GpuDriverPostProcessing("AMD", "Radeon Image Sharpening", True),
        ]

        with patch.object(start_controller_module, 'communicate', fake_communicate), \
                patch('ok.util.gpu_driver_settings.get_enabled_gpu_driver_post_processing',
                      return_value=enabled_features):
            controller.check_gpu_driver_post_processing()

        warning, title, *args = emit.call_args.args
        self.assertEqual(
            'NVIDIA RTX HDR is enabled and may cause malfunctions!\n'
            'AMD Radeon Image Sharpening is enabled and may cause malfunctions!',
            warning,
        )
        self.assertEqual('GPU Driver Warning', title)


if __name__ == '__main__':
    unittest.main()
