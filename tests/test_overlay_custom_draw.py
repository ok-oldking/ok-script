import os
import threading
import unittest
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QApplication

from ok import og
from ok.gui.overlay.OverlayWindow import OverlayWindow


class TestOverlayCustomDraw(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.original_app = getattr(og, 'app', None)
        self.original_device_manager = getattr(og, 'device_manager', None)
        self.original_ok = getattr(og, 'ok', None)
        self.original_config = getattr(og, 'config', None)
        og.app = SimpleNamespace(ok_config={'use_overlay': False})
        og.device_manager = SimpleNamespace(width=100, height=100)
        og.ok = SimpleNamespace(screenshot=SimpleNamespace(ui_dict={}))
        og.config = {}
        self.source_window = SimpleNamespace(
            visible=True,
            x=10,
            y=20,
            real_x_offset=2,
            real_y_offset=4,
            window_width=100,
            window_height=80,
            width=100,
            height=80,
            scaling=2,
        )
        self.view = OverlayWindow(self.source_window)

    def tearDown(self):
        self.view.close()
        self.view.deleteLater()
        QApplication.processEvents()
        og.app = self.original_app
        og.device_manager = self.original_device_manager
        og.ok = self.original_ok
        og.config = self.original_config

    def test_initializes_from_current_source_window_state(self):
        # update_overlay 用真实屏幕 DPR 做物理 -> 逻辑换算（修复混合 DPI 多屏偏移），
        # 期望值由同一换算函数计算，避免在 DPR 不同的主机上断言写死数值；
        # 同时验证几何确实是该换算的输出（而不是旧的 物理/scaling）。
        from ok.util.screen_coords import physical_rect_to_logical
        lx, ly, lw, lh = physical_rect_to_logical(12, 24, 100, 80, dpr_hint=2)
        expected = (int(round(lx)), int(round(ly)), max(1, int(round(lw))), max(1, int(round(lh))))

        geometry = self.view.geometry()

        self.assertTrue(self.view._source_visible)
        self.assertEqual(expected, (geometry.x(), geometry.y(), geometry.width(), geometry.height()))

    def test_custom_painter_controls_visibility_without_boxes_enabled(self):
        painted = []

        def paint(painter, view):
            painted.append(view)
            painter.setPen(QPen(QColor('green'), 2))
            painter.drawRect(2, 2, 20, 20)

        self.assertFalse(self.view.isVisible())

        worker = threading.Thread(target=lambda: self.view.draw('status', paint))
        worker.start()
        worker.join()
        QApplication.processEvents()
        self.view.repaint()

        self.assertTrue(self.view.isVisible())
        self.assertIn(self.view, painted)

        worker = threading.Thread(target=lambda: self.view.clear_draw('status'))
        worker.start()
        worker.join()
        QApplication.processEvents()

        self.assertFalse(self.view.isVisible())

    def test_enabled_overlay_stays_visible_without_active_content(self):
        self.assertFalse(self.view.isVisible())

        self.view.set_boxes_enabled(True)
        QApplication.processEvents()

        self.assertTrue(self.view.isVisible())

        self.view.clear_drawing()
        QApplication.processEvents()

        self.assertTrue(self.view.isVisible())

        self.view.set_boxes_enabled(False)
        QApplication.processEvents()

        self.assertFalse(self.view.isVisible())

    def test_enabled_overlay_hides_when_source_window_is_not_visible(self):
        self.view.set_boxes_enabled(True)
        QApplication.processEvents()

        self.assertTrue(self.view.isVisible())

        self.view.update_overlay(False, 0, 0, 100, 100, 100, 100, 1)
        QApplication.processEvents()

        self.assertFalse(self.view.isVisible())

    def test_blur_patches_are_cleared_when_game_leaves_foreground(self):
        patch = np.zeros((10, 20, 3), dtype=np.uint8)
        self.view.update_blur_patches([(0, 0, 20, 10, patch)])
        self.assertTrue(self.view.isVisible())

        self.view.update_overlay(False, 0, 0, 100, 100, 100, 100, 1)

        self.assertFalse(self.view.blur_images)
        self.assertFalse(self.view.isVisible())
