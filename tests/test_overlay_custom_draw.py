import unittest
from types import SimpleNamespace

import numpy as np

from ok import og
from ok.ui.overlay import Win32GdiOverlay


class TestWin32GdiOverlay(unittest.TestCase):
    def setUp(self):
        self.original_app = getattr(og, 'app', None)
        self.original_ok = getattr(og, 'ok', None)
        og.app = SimpleNamespace(ok_config={'use_overlay': False, 'show_overlay_logs': True})
        og.ok = SimpleNamespace(screenshot=SimpleNamespace(ui_dict={}))
        self.source_window = SimpleNamespace(
            visible=True, x=10, y=20, real_x_offset=2, real_y_offset=4,
            window_width=100, window_height=80, width=100, height=80, scaling=2,
        )
        # State tests must not create a real click-through desktop window.
        self.view = Win32GdiOverlay(self.source_window, native=False)

    def tearDown(self):
        self.view.close()
        og.app = self.original_app
        og.ok = self.original_ok

    def test_initializes_from_current_source_window_state(self):
        self.assertTrue(self.view._source_visible)
        self.assertEqual((12, 24, 100, 80),
                         (self.view._x, self.view._y, self.view._width, self.view._height))

    def test_custom_painter_controls_visibility_without_boxes_enabled(self):
        self.assertFalse(self.view.isVisible())
        self.view.draw('status', lambda canvas, view: canvas.rectangle(2, 2, 20, 20))
        self.assertTrue(self.view.isVisible())
        self.view.clear_draw('status')
        self.assertFalse(self.view.isVisible())

    def test_enabled_overlay_stays_visible_without_active_content(self):
        self.view.set_boxes_enabled(True)
        self.assertTrue(self.view.isVisible())
        self.view.clear_drawing()
        self.assertTrue(self.view.isVisible())
        self.view.set_boxes_enabled(False)
        self.assertFalse(self.view.isVisible())

    def test_background_detection_is_hidden_when_source_window_is_not_foreground(self):
        self.view.set_boxes_enabled(True)
        self.view.update_overlay(False, 0, 0, 100, 100, 100, 100, 1)
        self.assertFalse(self.view.isVisible())
        self.view.on_draw_box("feature", [object()], "red", None, True)
        self.assertFalse(self.view.isVisible())

    def test_blur_patches_are_cleared_when_game_leaves_foreground(self):
        patch = np.zeros((10, 20, 3), dtype=np.uint8)
        self.view.update_blur_patches([(0, 0, 20, 10, patch)])
        self.assertTrue(self.view.isVisible())
        self.view.update_overlay(False, 0, 0, 100, 100, 100, 100, 1)
        self.assertFalse(self.view.blur_images)
        self.assertFalse(self.view.isVisible())
