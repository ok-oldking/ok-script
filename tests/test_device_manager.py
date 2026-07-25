import unittest
from unittest.mock import Mock, patch

from ok.device.DeviceManager import DeviceManager


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
