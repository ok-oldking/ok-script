import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from ok.device.capture_methods.browser import BrowserCaptureMethod, BrowserWGC, BrowserWindowAdapter


class TestBrowserGeometry(unittest.TestCase):
    def capture(self):
        capture = BrowserCaptureMethod.__new__(BrowserCaptureMethod)
        capture.hwnd = 10
        capture._size = (1920, 1080)
        capture.get_viewport_rect = Mock(return_value=(1640, 406, 3560, 1486))
        return capture

    def test_window_grows_to_fit_viewport_below_infobar_without_moving(self):
        capture = self.capture()
        with patch('ok.device.capture_methods.browser.win32gui.ClientToScreen', return_value=(1640, 263)), \
                patch('ok.device.capture_methods.browser.win32gui.GetClientRect', return_value=(0, 0, 1920, 1206)), \
                patch('ok.device.capture_methods.browser.win32gui.GetWindowRect', return_value=(1632, 263, 3568, 1477)), \
                patch('ok.device.capture_methods.browser.win32gui.SetWindowPos') as resize:
            self.assertFalse(capture.update_window_geometry())
        self.assertEqual((0, 143), (capture.x_offset, capture.y_offset))
        self.assertEqual((1936, 1231), resize.call_args.args[4:6])

    def test_fitting_viewport_does_not_resize(self):
        capture = self.capture()
        with patch('ok.device.capture_methods.browser.win32gui.ClientToScreen', return_value=(1640, 263)), \
                patch('ok.device.capture_methods.browser.win32gui.GetClientRect', return_value=(0, 0, 1920, 1223)), \
                patch('ok.device.capture_methods.browser.win32gui.SetWindowPos') as resize:
            self.assertTrue(capture.update_window_geometry())
        resize.assert_not_called()

    def test_absolute_coordinates_include_native_client_border(self):
        capture = SimpleNamespace(hwnd=10, x_offset=0, y_offset=143)
        with patch('ok.device.capture_methods.browser.win32gui.ClientToScreen', return_value=(1740, 606)) as convert:
            self.assertEqual((1740, 606), BrowserWindowAdapter(capture).get_abs_cords(100, 200))
        convert.assert_called_once_with(10, (100, 343))

    def test_renderer_bounds_skip_hidden_windows_and_browser_controls(self):
        capture = BrowserCaptureMethod.__new__(BrowserCaptureMethod)
        capture.hwnd = 10

        def enumerate_children(_hwnd, callback, context):
            for hwnd in (11, 12, 13):
                callback(hwnd, context)

        with patch('ok.device.capture_methods.browser.win32gui.EnumChildWindows', side_effect=enumerate_children), \
                patch('ok.device.capture_methods.browser.win32gui.IsWindowVisible', side_effect=lambda hwnd: hwnd != 11), \
                patch('ok.device.capture_methods.browser.win32gui.GetClassName',
                      side_effect=lambda hwnd: 'Chrome_RenderWidgetHostHWND' if hwnd == 13 else 'ToolbarWindow32'), \
                patch('ok.device.capture_methods.browser.win32gui.GetClientRect', return_value=(0, 0, 1920, 1080)), \
                patch('ok.device.capture_methods.browser.win32gui.ClientToScreen', return_value=(1640, 406)):
            self.assertEqual((1640, 406, 3560, 1486), capture.get_viewport_rect())

    def crop(self, frame):
        capture = SimpleNamespace(hwnd=10, x_offset=0, y_offset=143, width=1920, height=1080)
        method = BrowserWGC.__new__(BrowserWGC)
        method.browser_method = capture
        method._hwnd_window = BrowserWindowAdapter(capture)

        def bounds(_hwnd, _attribute, pointer, _size):
            rect = pointer._obj
            rect.left, rect.top, rect.right, rect.bottom = 1638, 263, 3562, 1488
            return 0

        with patch('ok.device.capture_methods.browser.ctypes.windll.dwmapi.DwmGetWindowAttribute', side_effect=bounds), \
                patch('ok.device.capture_methods.browser.win32gui.ClientToScreen', return_value=(1640, 406)):
            return method.crop_image(frame)

    def test_crop_uses_renderer_origin_instead_of_assuming_symmetric_borders(self):
        frame = np.arange(1225 * 1924, dtype=np.int32).reshape(1225, 1924)
        result = self.crop(frame)
        self.assertEqual((1080, 1920), result.shape)
        np.testing.assert_array_equal(frame[143:1223, 2:1922], result)

    def test_clipped_viewport_is_rejected_instead_of_shifting_crop_up(self):
        self.assertIsNone(self.crop(np.zeros((1208, 1924), dtype=np.uint8)))


if __name__ == '__main__':
    unittest.main()
