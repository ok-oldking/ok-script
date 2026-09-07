import unittest
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ok.device.DeviceManager import DeviceManager, resolve_emulator_window_exe
from ok.device.window_target import (
    StableWindowHint,
    WindowCandidate,
    WindowGeometry,
    WindowMatchHints,
    WindowSelectionResult,
    WindowSelectionStatus,
)


class TestEmulatorWindowExe(unittest.TestCase):
    def test_resolves_mumu_15_instance_window(self):
        launcher = r'C:\Program Files\Netease\MuMu\nx_main\MuMuNxMain.exe'

        result = resolve_emulator_window_exe(launcher, 'MuMuPlayer-15.0-1')

        self.assertEqual(
            r'C:\Program Files\Netease\MuMu\nx_device\15.0\shell\MuMuNxDevice.exe',
            result)

    def test_resolves_mumu_12_instance_window(self):
        launcher = r'C:\MuMu\nx_main\MuMuNxMain.exe'

        result = resolve_emulator_window_exe(launcher, 'MuMuPlayer-12.0-0')

        self.assertEqual(
            r'C:\MuMu\nx_device\12.0\shell\MuMuNxDevice.exe', result)

    def test_keeps_other_emulator_executable(self):
        executable = r'C:\LDPlayer\dnplayer.exe'

        self.assertEqual(
            executable,
            resolve_emulator_window_exe(executable, 'leidian0'))


class TestDeviceManagerInteractionSelection(unittest.TestCase):
    def test_adb_interaction_selection_does_not_require_windows_backend(self):
        manager = DeviceManager.__new__(DeviceManager)
        manager.config = {'preferred': 'phone', 'interaction': ''}
        manager.device_dict = {'phone': {'imei': 'phone', 'device': 'adb'}}
        manager.windows_capture_config = None
        manager.win_interaction_class = None
        manager.start = Mock()

        manager.set_interaction('ADBInteraction')

        self.assertEqual('ADBInteraction', manager.config['interaction'])
        self.assertIsNone(manager.win_interaction_class)
        manager.start.assert_called_once_with()

    def test_close_invalidates_input_before_capture(self):
        calls = []
        interaction = Mock()
        manager = DeviceManager.__new__(DeviceManager)

        def destroy():
            self.assertIs(manager.interaction, interaction)
            calls.append(("destroy",))

        interaction.on_destroy.side_effect = destroy
        capture = Mock()
        capture.close.side_effect = lambda: calls.append(("capture",))
        manager.interaction = interaction
        manager.capture_method = capture
        manager.hwnd_window = None

        manager.close()

        self.assertEqual(
            [
                ("destroy",),
                ("capture",),
            ],
            calls,
        )
        self.assertIsNone(manager.interaction)
        self.assertIsNone(manager.capture_method)

    def test_macos_input_invalidation_pauses_executor_with_gate_closed(self):
        manager = DeviceManager.__new__(DeviceManager)
        manager.executor = Mock()
        manager.exit_event = Mock()
        manager.exit_event.is_set.return_value = False

        manager._on_macos_interaction_invalidated("game lost focus")

        manager.executor.pause.assert_called_once_with()

    def test_close_fallback_permanently_shuts_down_failed_interaction(self):
        interaction = Mock()
        interaction.on_destroy.side_effect = RuntimeError("destroy failed")
        manager = DeviceManager.__new__(DeviceManager)
        manager.interaction = interaction
        manager.capture_method = None
        manager.hwnd_window = None

        manager.close()

        interaction.invalidate.assert_called_once_with(
            "device manager closing", shutdown=True)

    def test_do_start_is_rejected_after_close_begins(self):
        manager = DeviceManager.__new__(DeviceManager)
        manager._device_lifecycle_lock = threading.RLock()
        manager._closing = True
        manager.exit_event = Mock()
        manager.exit_event.is_set.return_value = False
        manager._do_start_locked = Mock()

        manager.do_start(notify=False)

        manager._do_start_locked.assert_not_called()

    def test_replaced_macos_capture_cannot_invalidate_new_interaction(self):
        manager = DeviceManager.__new__(DeviceManager)
        current_capture = object()
        replaced_capture = object()
        manager.capture_method = current_capture
        manager.interaction = Mock()

        manager._on_macos_capture_input_invalidated(
            replaced_capture, "late old-stream callback")
        manager.interaction.invalidate.assert_not_called()

        manager._on_macos_capture_input_invalidated(
            current_capture, "current stream stopped")
        manager.interaction.invalidate.assert_called_once_with(
            "current stream stopped")


class TestDeviceManagerMacOSWindowSelection(unittest.TestCase):
    def make_manager(self, selection):
        discovery = Mock()
        discovery.select.return_value = selection
        bound_target = Mock()
        bound_target.exists.return_value = selection.selected is not None
        bound_target.snapshot = SimpleNamespace(candidate=selection.selected)
        discovery.bind.return_value = bound_target
        manager = DeviceManager.__new__(DeviceManager)
        manager.macos_window_config = {
            'bundle_identifiers': [],
            'application_names': [],
            'title_patterns': ['Game'],
            'allowed_layers': [0],
        }
        manager.config = {'macos_target_hint': {}}
        manager.window_discovery = discovery
        manager.permission_service = Mock()
        manager.window_target = None
        manager.device_dict = {}
        return manager, discovery

    def test_manual_selection_persists_only_stable_identity(self):
        selected = WindowCandidate(
            process_id=42,
            window_id=7,
            bundle_identifier='com.example.game',
            application_name='Example Game',
            title='Game',
            layer=0,
            outer_geometry=WindowGeometry(0, 0, 1280, 720),
        )
        selection = WindowSelectionResult(
            WindowSelectionStatus.SELECTED, (selected,), selected)
        manager, discovery = self.make_manager(selection)

        with patch('ok.device.DeviceManager.require_platform'):
            result = manager.bind_macos_window(manual_window_id=7)

        self.assertIs(result, selection)
        self.assertIs(manager.window_target, discovery.bind.return_value)
        self.assertEqual({
            'bundle_identifier': 'com.example.game',
            'application_name': 'Example Game',
            'title': 'Game',
        }, manager.config['macos_target_hint'])
        self.assertNotIn('process_id', manager.config['macos_target_hint'])
        self.assertNotIn('window_id', manager.config['macos_target_hint'])
        self.assertFalse(manager.device_dict['macos']['connected'])
        self.assertTrue(manager.device_dict['macos']['target_bound'])
        self.assertEqual(42, manager.device_dict['macos']['process_id'])
        discovery.select.assert_called_once_with(
            WindowMatchHints(
                title_patterns=('Game',),
                allowed_layers=(0,),
            ),
            stable_hint=StableWindowHint(),
            manual_window_id=7,
        )

    def test_ambiguous_selection_does_not_leave_a_stale_target(self):
        selection = WindowSelectionResult(
            WindowSelectionStatus.MANUAL_SELECTION_REQUIRED, ())
        manager, discovery = self.make_manager(selection)
        manager.window_target = object()

        with patch('ok.device.DeviceManager.require_platform'):
            result = manager.bind_macos_window()

        self.assertIs(result, selection)
        self.assertIsNone(manager.window_target)
        self.assertFalse(manager.device_dict['macos']['target_bound'])
        discovery.bind.assert_not_called()

    def test_macos_device_starts_capture_and_foreground_interaction(self):
        class FakeCapture:
            def __init__(
                    self, _exit_event, target, _permission_service,
                    on_input_invalidated=None):
                self.target = target
                self.closed = False
                self.on_input_invalidated = on_input_invalidated

            def close(self):
                self.closed = True

            def connected(self):
                return True

            def diagnostics(self):
                return SimpleNamespace(state=SimpleNamespace(value='running'))

        class FakeInteraction:
            def __init__(
                    self, capture, target, _permission_service,
                    *, exit_event=None, on_invalidated=None):
                self.capture = capture
                self.target = target
                self.exit_event = exit_event
                self.on_invalidated = on_invalidated
                self.cursor_service = SimpleNamespace(available=True)

            def get_capabilities(self):
                from ok.device.capabilities import DeviceCapabilities
                return DeviceCapabilities(keyboard_tap=True, foreground_only=True)

            def on_destroy(self):
                pass

        manager = DeviceManager.__new__(DeviceManager)
        manager.macos_window_config = {'title_patterns': ['Game']}
        manager.device_dict = {
            'macos': {
                'imei': 'macos',
                'device': 'macos',
                'connected': False,
            },
        }
        manager.config = {'preferred': 'macos'}
        manager.window_target = Mock()
        manager.window_target.exists.return_value = True
        manager.window_target.snapshot = SimpleNamespace(exists=True, candidate=None)
        manager.window_discovery = Mock()
        manager.permission_service = Mock()
        manager.exit_event = Mock()
        manager.capture_method = Mock()
        previous_capture = manager.capture_method
        manager.interaction = object()
        manager.cursor_service = SimpleNamespace(available=False)

        with (
                patch('ok.device.DeviceManager.require_platform'),
                # Inject synthetic exports without resolving the real lazy
                # macOS export first (which correctly rejects Windows hosts).
                patch.dict('ok.device.capture_methods.__dict__',
                           ScreenCaptureKitCaptureMethod=FakeCapture),
                patch.dict('ok.device.interaction_methods.__dict__',
                           QuartzForegroundInteraction=FakeInteraction),
        ):
            manager.do_start(notify=False)

        previous_capture.close.assert_called_once_with()
        self.assertIsInstance(manager.capture_method, FakeCapture)
        self.assertIsInstance(manager.interaction, FakeInteraction)
        self.assertIs(manager.cursor_service, manager.interaction.cursor_service)
        self.assertIs(
            manager.capture_method.on_input_invalidated.__self__, manager)
        self.assertTrue(manager.device_dict['macos']['target_bound'])
        self.assertTrue(manager.device_dict['macos']['connected'])
        self.assertEqual(['ScreenCaptureKit'], manager.available_capture_methods())
        self.assertEqual(
            ['QuartzForegroundInteraction'],
            manager.available_interaction_methods(),
        )
        self.assertTrue(manager.device_connected())

        manager.window_target.exists.return_value = False
        manager.update_macos_device()
        self.assertFalse(manager.device_dict['macos']['target_bound'])
        self.assertFalse(manager.device_dict['macos']['connected'])


class TestDeviceManagerPcWindows(unittest.TestCase):
    def make_manager(self):
        manager = DeviceManager.__new__(DeviceManager)
        manager.windows_capture_config = {
            'title': 'Game',
            'exe': ['game.exe'],
        }
        manager.config = {
            'selected_exe': '',
            'selected_hwnd': 0,
            'pc_full_path': '',
        }
        manager.device_dict = {
            'phone': {'imei': 'phone', 'device': 'adb'},
            'pc_101': {'imei': 'pc_101', 'device': 'windows', 'real_hwnd': 101},
        }
        return manager

    def test_update_pc_device_replaces_window_with_new_hwnd(self):
        manager = self.make_manager()
        found_window = ('Game', 202, r'C:\Game\game.exe', 0, 0, 1920, 1080, [])

        with patch('ok.device.DeviceManager.find_hwnd', return_value=found_window):
            manager.update_pc_device()

        self.assertEqual({'phone', 'pc_202'}, set(manager.device_dict))
        self.assertEqual(202, manager.device_dict['pc_202']['real_hwnd'])

    def test_update_pc_device_removes_old_hwnd_when_window_closes(self):
        manager = self.make_manager()
        missing_window = (None, 0, None, 0, 0, 0, 0, [])

        with patch('ok.device.DeviceManager.find_hwnd', return_value=missing_window):
            manager.update_pc_device()

        self.assertEqual({'phone', 'pc'}, set(manager.device_dict))
        self.assertFalse(manager.device_dict['pc']['connected'])

    def test_get_exe_path_uses_calculated_path_when_saved_path_is_empty(self):
        manager = self.make_manager()
        calculate = Mock(return_value=r'C:\Game\game.exe')
        manager.windows_capture_config['calculate_pc_exe_path'] = calculate
        device = {'device': 'windows', 'full_path': ''}

        with patch('ok.device.DeviceManager.os.path.exists', return_value=True):
            with patch('ok.device.DeviceManager.logger.info') as log:
                path = manager.get_exe_path(device)

        calculate.assert_called_once_with(None)
        log.assert_any_call(
            r'calculate_pc_exe_path caller path None, result C:\Game\game.exe')
        self.assertEqual(r'C:\Game\game.exe', path)

    def test_get_exe_path_returns_none_when_calculated_path_does_not_exist(self):
        manager = self.make_manager()
        calculate = Mock(return_value=r'C:\Game\missing.exe')
        manager.windows_capture_config['calculate_pc_exe_path'] = calculate
        device = {'device': 'windows', 'full_path': None}

        with patch('ok.device.DeviceManager.os.path.exists', return_value=False):
            path = manager.get_exe_path(device)

        calculate.assert_called_once_with(None)
        self.assertIsNone(path)

    def test_get_exe_path_returns_none_when_calculation_raises(self):
        manager = self.make_manager()
        calculate = Mock(side_effect=RuntimeError('registry lookup failed'))
        manager.windows_capture_config['calculate_pc_exe_path'] = calculate
        device = {'device': 'windows', 'full_path': None}

        path = manager.get_exe_path(device)

        calculate.assert_called_once_with(None)
        self.assertIsNone(path)


if __name__ == '__main__':
    unittest.main()
