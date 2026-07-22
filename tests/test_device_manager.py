import unittest
from unittest.mock import patch

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


if __name__ == '__main__':
    unittest.main()
