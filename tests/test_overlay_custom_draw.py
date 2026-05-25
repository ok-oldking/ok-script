import os
import threading
import unittest
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

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
        self.view = OverlayWindow(None)
        self.view.update_overlay(True, 0, 0, 100, 100, 100, 100, 1)

    def tearDown(self):
        self.view.close()
        self.view.deleteLater()
        QApplication.processEvents()
        og.app = self.original_app
        og.device_manager = self.original_device_manager
        og.ok = self.original_ok
        og.config = self.original_config

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
