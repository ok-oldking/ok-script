import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ok.ui.qt.MainWindow import MainWindow, fit_window_size
from ok.ui.qt.kit import NavigationView
from ok.ui.qt.kit.navigation import COMPACT_WIDTH, EXPANDED_WIDTH


class _NavigationStateHarness:
    apply_navigation_state = MainWindow.apply_navigation_state
    _save_navigation_state = MainWindow._save_navigation_state

    def __init__(self, expanded):
        self.navigation = NavigationView()
        self.ok_config = {'navigation_expanded': expanded}
        self.navigation.compact_changed.connect(self._save_navigation_state)


class TestNavigationState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_saved_state_is_applied(self):
        expanded = _NavigationStateHarness(expanded=True)
        expanded.apply_navigation_state()
        self.assertEqual(EXPANDED_WIDTH, expanded.navigation.width())

        compact = _NavigationStateHarness(expanded=False)
        compact.apply_navigation_state()
        self.assertTrue(compact.navigation.is_compact())
        self.assertEqual(COMPACT_WIDTH, compact.navigation.width())

    def test_collapse_button_saves_state(self):
        harness = _NavigationStateHarness(expanded=True)
        harness.navigation.collapse_button.click()
        self.assertFalse(harness.ok_config['navigation_expanded'])
        harness.navigation.collapse_button.click()
        self.assertTrue(harness.ok_config['navigation_expanded'])


class TestFitWindowSize(unittest.TestCase):
    def test_default_size_fits_1600x900_with_taskbar(self):
        from ok.core.ui_config import DEFAULT_WINDOW_SIZE
        size = DEFAULT_WINDOW_SIZE
        self.assertEqual((size["width"], size["height"]), (size["min_width"], size["min_height"]))
        self.assertLessEqual(size["width"], 1600)
        self.assertEqual((size["width"], 820, size["width"], 820), fit_window_size(
            size["width"], size["height"], size["min_width"], size["min_height"], 1600, 852))

    def test_oversized_request_is_clamped_to_the_screen(self):
        self.assertEqual((1280, 680, 1280, 680), fit_window_size(1440, 820, 1440, 820, 1280, 680))

    def test_size_never_below_minimum(self):
        self.assertEqual((1000, 700, 1000, 700), fit_window_size(800, 600, 1000, 700, 1920, 1040))


if __name__ == '__main__':
    unittest.main()
