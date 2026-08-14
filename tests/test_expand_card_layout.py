import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from qfluentwidgets import ExpandLayout, ExpandSettingCard, FluentIcon

from ok.gui.widget.ExpandCardLayout import ExpandCardLayout


class TestExpandCardLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_expanding_card_is_a_direct_child_of_the_official_layout(self):
        host = QWidget()
        layout = ExpandCardLayout(host)
        card = ExpandSettingCard(FluentIcon.INFO, "Card")
        card.viewLayout.addWidget(QLabel("Animated content"))

        layout.addWidget(card)
        host.resize(600, 400)
        host.show()
        QApplication.processEvents()
        self.addCleanup(host.close)

        self.assertIsInstance(layout, ExpandLayout)
        self.assertIs(card.parentWidget(), host)

        collapsed_height = card.height()
        card.setExpand(True)
        QTest.qWait(300)
        self.assertGreater(card.height(), collapsed_height)

        layout.removeWidget(card)
        self.assertEqual(0, layout.count())

    def test_cards_can_be_removed(self):
        host = QWidget()
        layout = ExpandCardLayout(host)
        first = QLabel("First")
        second = QLabel("Second")

        layout.addWidget(first)
        layout.addWidget(second)
        self.assertEqual(2, layout.count())
        self.assertIs(first, layout.itemAt(0).widget())
        self.assertIs(second, layout.itemAt(1).widget())

        layout.removeWidget(second)
        self.assertEqual(1, layout.count())
        self.assertIs(first, layout.itemAt(0).widget())


if __name__ == "__main__":
    unittest.main()
