import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import FluentIcon, FluentWindow, NavigationDisplayMode

from ok.gui.MainWindow import MainWindow


class _NavigationStateHarness:
    apply_navigation_state = MainWindow.apply_navigation_state
    update_navigation_width = MainWindow.update_navigation_width
    _expand_navigation_without_animation = MainWindow._expand_navigation_without_animation

    def __init__(self, navigation_interface, expanded):
        self.navigationInterface = navigation_interface
        self.ok_config = {'navigation_expanded': expanded}


class TestNavigationState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_expanded_width_is_applied_before_first_show(self):
        window = FluentWindow()
        window.resize(1600, 900)

        page = QWidget()
        page.setObjectName('capture')
        window.addSubInterface(page, FluentIcon.PLAY, 'Capture')

        harness = _NavigationStateHarness(window.navigationInterface, expanded=True)
        harness.apply_navigation_state()

        panel = window.navigationInterface.panel
        self.assertEqual(panel.displayMode, NavigationDisplayMode.EXPAND)
        self.assertGreater(panel.width(), 48)
        self.assertEqual(window.navigationInterface.width(), panel.width())


if __name__ == '__main__':
    unittest.main()
