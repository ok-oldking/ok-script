import unittest
from types import SimpleNamespace

from ok.device.capture_methods.browser import BrowserWindowAdapter
from ok.device.capture_methods.hwnd_window import HwndWindow


class TestCaptureTargetSignature(unittest.TestCase):
    def test_hwnd_window_signature_tracks_hwnd_tree_and_geometry(self):
        window = object.__new__(HwndWindow)
        window.hwnd = 10
        window.top_hwnd = 11
        window.width = 1280
        window.height = 720
        window.real_x_offset = 0
        window.real_y_offset = 32
        window.real_width = 1280
        window.real_height = 720
        window.hwnds = [(10,), (11,)]

        original = window.capture_target_signature

        window.hwnds = [(10,), (12,)]
        self.assertNotEqual(original, window.capture_target_signature)

        window.hwnds = [(10,), (11,)]
        window.real_y_offset = 0
        self.assertNotEqual(original, window.capture_target_signature)

    def test_browser_window_adapter_exposes_capture_target_signature(self):
        browser_capture = SimpleNamespace(
            hwnd=10,
            top_hwnd=11,
            width=1280,
            height=720,
            x_offset=0,
            y_offset=32,
            exe_full_path='browser.exe',
        )
        adapter = BrowserWindowAdapter(browser_capture)

        self.assertEqual((10, 1280, 720, 0, 32, 'browser.exe'), adapter.capture_target_signature)


if __name__ == '__main__':
    unittest.main()
