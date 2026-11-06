import os
import unittest
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QWidget

from ok.ui.qt.shell.lazy_page import LazyPage


class TestLazyPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_builds_once_on_first_use(self):
        factory = Mock(side_effect=QWidget)
        lazy = LazyPage(factory)

        self.assertFalse(lazy.is_built())
        factory.assert_not_called()

        page = lazy.page()
        self.assertIs(page, lazy.page())
        self.assertIs(lazy, page.parentWidget())
        factory.assert_called_once_with()

    def test_dispose_skips_unbuilt_page(self):
        factory = Mock(side_effect=QWidget)
        LazyPage(factory).dispose()

        factory.assert_not_called()

    def test_dispose_forwards_to_built_page(self):
        page = QWidget()
        page.dispose = Mock()
        lazy = LazyPage(lambda: page)
        lazy.page()

        lazy.dispose()

        page.dispose.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
