import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import ok.ui.qt.StartController as start_controller_module
from ok.ui.qt.StartController import StartController
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
        controller.config = {}
        controller.start_method = 'start'
        controller.STARTED_WINDOW_STABLE_SECONDS = 2
        controller.STARTED_WINDOW_POLL_INTERVAL = 1
        controller.starting = False
        return controller

    def test_start_marks_starting_before_background_handler_runs(self):
        controller = self.make_controller()
        controller.handler = Mock()

        controller.start()

        self.assertTrue(controller.starting)
        controller.handler.post.assert_called_once()

    def test_do_start_clears_starting_after_completion(self):
        controller = self.make_controller()
        controller._do_start = Mock(return_value=True)

        self.assertTrue(controller.do_start())

        self.assertFalse(controller.starting)

    def test_capture_refresh_timeout_closes_loading_and_reports_error(self):
        controller = self.make_controller()
        controller.start_exe = True
        controller.tr = lambda message: message
        message = 'Windows Graphics Capture is busy, please retry starting the game'
        device_manager = SimpleNamespace(do_refresh=Mock(side_effect=TimeoutError(message)))
        emit = Mock()
        fake_communicate = SimpleNamespace(starting_emulator=SimpleNamespace(emit=emit))

        with patch.object(start_controller_module, 'og', SimpleNamespace(device_manager=device_manager)), \
                patch.object(start_controller_module, 'communicate', fake_communicate):
            self.assertFalse(controller.do_start())

        self.assertFalse(controller.starting)
        self.assertEqual((False, None, controller.start_timeout), emit.call_args_list[0].args)
        self.assertEqual((True, message, 0), emit.call_args_list[-1].args)

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
        controller.start_method = 'os.startfile'
        execute = Mock(side_effect=lambda *args, **kwargs: call_order.append('execute') or True)

        with patch.object(start_controller_module, 'og', fake_og), \
                patch.object(start_controller_module, 'is_admin', return_value=True), \
                patch.object(start_controller_module, 'execute', execute):
            self.assertTrue(controller.start_device())

        self.assertEqual(['execute', 'stable', 'ready'], call_order)
        execute.assert_called_once_with(r'C:\game.exe', arguments=None, start_method='os.startfile')

    def make_launch_context(self, device_type='windows', connected=False, dx11=False):
        controller = self.make_controller()
        controller._wait_until_started_window_stable = Mock(return_value=True)
        controller._wait_until_device_ready = Mock(return_value=True)
        device_manager = Mock()
        device_manager.get_preferred_device.return_value = {
            'connected': connected,
            'device': device_type,
        }
        device_manager.get_exe_path.return_value = r'C:\game.exe'
        fake_og = SimpleNamespace(device_manager=device_manager, global_config=Mock())
        fake_og.global_config.get_config.return_value = {'Launch with DX11': dx11}
        return controller, fake_og

    def test_launch_arguments_preserve_dx11_and_launch_method(self):
        for start_method in ('start', 'os.startfile'):
            for dx11 in (False, True):
                for extra_args in ('-custom="value with spaces"', None, '', lambda: '-custom', lambda: None):
                    with self.subTest(start_method=start_method, dx11=dx11, extra_args=extra_args):
                        controller, fake_og = self.make_launch_context(dx11=dx11)
                        controller.start_method = start_method
                        controller.config = {'windows': {'launch_arguments': extra_args}}
                        expected_args = '-dx11 -d3d11 -force-d3d11' if dx11 else None
                        extra = extra_args() if callable(extra_args) else extra_args
                        if extra:
                            expected_args = f'{expected_args or ""} {extra}'.strip()

                        with patch.object(start_controller_module, 'og', fake_og), \
                                patch.object(start_controller_module, 'is_admin', return_value=True), \
                                patch.object(start_controller_module, 'execute', return_value=True) as execute:
                            self.assertTrue(controller.start_device())

                        execute.assert_called_once_with(
                            r'C:\game.exe', arguments=expected_args, start_method=start_method)

    def test_launch_arguments_callback_reads_current_settings_on_each_launch(self):
        controller, fake_og = self.make_launch_context()
        settings = {'package': 'hd'}
        callback = Mock(side_effect=lambda: f'-krqlv={settings["package"]}')
        controller.config = {'windows': {'launch_arguments': callback}}

        with patch.object(start_controller_module, 'og', fake_og), \
                patch.object(start_controller_module, 'is_admin', return_value=True), \
                patch.object(start_controller_module, 'execute', return_value=True) as execute:
            self.assertTrue(controller.start_device())
            self.assertEqual('-krqlv=hd', execute.call_args.kwargs['arguments'])
            settings['package'] = 'uhd'
            self.assertTrue(controller.start_device())
            self.assertEqual('-krqlv=uhd', execute.call_args.kwargs['arguments'])

        self.assertEqual([unittest.mock.call(), unittest.mock.call()], callback.call_args_list)

    def test_launch_arguments_callback_is_skipped_for_connected_games_and_adb(self):
        for device_type, connected in (('windows', True), ('adb', False)):
            with self.subTest(device_type=device_type, connected=connected):
                controller, fake_og = self.make_launch_context(device_type, connected)
                callback = Mock(return_value='-windows-only')
                controller.config = {'windows': {'launch_arguments': callback}}

                with patch.object(start_controller_module, 'og', fake_og), \
                        patch.object(start_controller_module, 'execute', return_value=True) as execute:
                    self.assertTrue(controller.start_device())

                callback.assert_not_called()
                if connected:
                    execute.assert_not_called()
                else:
                    execute.assert_called_once_with(r'C:\game.exe', arguments=None, start_method='start')

    def test_gpu_driver_warning_identifies_each_enabled_vendor_feature(self):
        controller = self.make_controller()
        emit = Mock()
        fake_communicate = SimpleNamespace(notification=SimpleNamespace(emit=emit))
        fake_og = SimpleNamespace(device_manager=SimpleNamespace(
            hwnd_window=SimpleNamespace(exe_full_path=r'C:\game.exe', hwnd=123),
        ))
        enabled_features = [
            GpuDriverPostProcessing("NVIDIA", "RTX HDR", True),
            GpuDriverPostProcessing("AMD", "Radeon Image Sharpening", True),
        ]

        with patch.object(start_controller_module, 'communicate', fake_communicate), \
                patch.object(start_controller_module, 'og', fake_og), \
                patch('ok.util.gpu_driver_settings.get_enabled_gpu_driver_post_processing',
                      return_value=enabled_features) as get_enabled:
            controller.check_gpu_driver_post_processing()

        get_enabled.assert_called_once_with(r'C:\game.exe', 123)
        warning, title, *args = emit.call_args.args
        self.assertEqual(
            'NVIDIA RTX HDR is enabled and may cause malfunctions!\n'
            'AMD Radeon Image Sharpening is enabled and may cause malfunctions!',
            warning,
        )
        self.assertEqual('GPU Driver Warning', title)

    def test_resolution_mismatch_is_info_only_when_auto_resize_is_disabled(self):
        controller = self.make_controller()
        controller.config = {
            'supported_resolution': {
                'ratio': '16:9',
                'min_size': (1280, 720),
                'resize_to': [(1280, 720)],
                'force_ratio': True,
            },
        }
        controller.tr = lambda text: text
        capture_method = object()
        fake_og = SimpleNamespace(
            executor=SimpleNamespace(
                check_frame_and_resolution=Mock(return_value=(False, '1024x768')),
            ),
            device_manager=SimpleNamespace(capture_method=capture_method),
            global_config=SimpleNamespace(
                get_config=Mock(return_value={'Auto Resize Game Window': False}),
            ),
        )

        with patch.object(start_controller_module, 'og', fake_og), \
                patch.object(start_controller_module, 'BaseWindowsCaptureMethod', object), \
                patch.object(start_controller_module, 'alert_info') as alert_info, \
                patch.object(start_controller_module, 'alert_error') as alert_error:
            self.assertIsNone(controller.check_resolution())

        alert_info.assert_called_once()
        self.assertFalse(alert_info.call_args.kwargs.get('tray', False))
        alert_error.assert_not_called()


if __name__ == '__main__':
    unittest.main()
