import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

from ok import og
from ok.ui.overlay import Win32GdiOverlay


class TestWin32GdiOverlay(unittest.TestCase):
    def setUp(self):
        self.original_app = getattr(og, 'app', None)
        self.original_ok = getattr(og, 'ok', None)
        og.app = SimpleNamespace(ok_config={'use_overlay': False})
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

    def test_alt_crosshair_makes_overlay_visible_while_pointer_is_inside(self):
        self.assertFalse(self.view.isVisible())
        self.view.set_boxes_enabled(True)
        self.view._update_input_state(True, False, 62, 64)
        self.assertTrue(self.view.isVisible())
        self.assertEqual((50, 40), self.view._mouse_position)

        self.view._update_input_state(False, False, 62, 64)
        self.assertTrue(self.view.isVisible())
        self.assertEqual([], self.view._click_points)

    def test_alt_right_click_copies_one_point_then_a_rectangle(self):
        copied = []
        self.view._copy_to_clipboard = copied.append
        self.view.set_boxes_enabled(True)

        self.view._update_input_state(True, True, 22, 44)
        self.view._update_input_state(True, True, 52, 64)
        self.assertEqual(['0.100, 0.250'], copied)

        self.view._update_input_state(True, False, 52, 64)
        self.view._update_input_state(True, True, 52, 64)
        self.assertEqual(['0.100, 0.250', '0.100, 0.250, 0.400, 0.500'], copied)
        self.assertEqual([(10, 20), (40, 40)], self.view._click_points)

    def test_disabled_overlay_ignores_alt_and_right_click(self):
        copied = []
        self.view._copy_to_clipboard = copied.append

        self.view._update_input_state(True, True, 22, 44)

        self.assertFalse(self.view.isVisible())
        self.assertFalse(self.view._is_alt_down)
        self.assertEqual([], copied)

    def test_right_click_without_alt_does_not_copy(self):
        copied = []
        self.view._copy_to_clipboard = copied.append
        self.view._update_input_state(False, True, 22, 44)
        self.assertEqual([], copied)

    def test_hidden_source_does_not_capture_coordinates(self):
        copied = []
        self.view._copy_to_clipboard = copied.append
        self.view.update_overlay(False, 12, 24, 100, 80, 100, 80, 1)
        self.view._update_input_state(True, True, 22, 44)
        self.assertEqual([], copied)
        self.assertFalse(self.view.isVisible())

    def test_frequent_box_events_keep_one_bounded_expiry_job(self):
        self.view.set_boxes_enabled(True)
        for _ in range(2000):
            self.view.on_draw_box("feature", [object()], "red", None, True)

        with self.view._expiry_lock:
            self.assertEqual({"boxes"}, set(self.view._expiry_jobs))
        self.assertTrue(self.view._expiry_handler.thread.is_alive())

    def test_replacing_timed_draw_with_permanent_draw_cancels_old_expiry(self):
        self.view.draw("status", lambda *_: None, duration=30)
        self.view.draw("status", lambda *_: None)

        with self.view._expiry_lock:
            self.assertNotIn("custom:status", self.view._expiry_jobs)
        self.assertIn("status", self.view.custom_painters)

    def test_exit_event_stops_all_overlay_workers(self):
        from ok.util.handler import ExitEvent

        self.view.close()
        event = ExitEvent()
        self.view = Win32GdiOverlay(self.source_window, native=False, exit_event=event)
        event.set()
        self.view._expiry_handler.join(timeout=1)

        self.assertTrue(self.view._closed)
        self.assertFalse(self.view._expiry_handler.thread.is_alive())

    def test_exit_event_overlay_stop_does_not_join_workers(self):
        self.view._join_workers = Mock()

        self.view.stop()

        self.view._join_workers.assert_not_called()

    def test_dark_text_panel_is_translucent_and_clipped(self):
        pixels = np.full((8, 10, 4), 255, dtype=np.uint8)

        self.view._paint_dark_panel(pixels, -5, 2, 20, 7, alpha=180)

        np.testing.assert_array_equal(pixels[2:7, :, :3], 0)
        np.testing.assert_array_equal(pixels[2:7, :, 3], 180)
        np.testing.assert_array_equal(pixels[:2], 255)
        np.testing.assert_array_equal(pixels[7:], 255)
