import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon

from ok import og
from ok.gui.tasks.ConfigCard import ConfigCard


class FakeConfig(dict):
    def __init__(self, default):
        super().__init__(default)
        self.default = default

    def get_default(self, key):
        return self.default.get(key)

    def has_user_config(self):
        return not all(key.startswith("_") for key in self)


class TestConfigCard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.original_app = getattr(og, "app", None)
        og.app = SimpleNamespace(tr=lambda text: text)

    def tearDown(self):
        og.app = self.original_app

    def create_card(self, default):
        config = FakeConfig(default)
        card = ConfigCard(
            task=None,
            name="Task",
            config=config,
            description="Description",
            default_config=default,
            config_description={},
            config_type={},
            config_icon=FluentIcon.INFO,
        )
        card.resize(600, card.height())
        card.show()
        QApplication.processEvents()
        self.addCleanup(card.close)
        return card

    def test_empty_config_card_does_not_expand_when_header_is_clicked(self):
        card = self.create_card({})

        self.assertTrue(card.card.expandButton.isHidden())
        QTest.mouseClick(card.card, Qt.LeftButton)
        QApplication.processEvents()

        self.assertFalse(card.isExpand)

    def test_config_card_with_content_still_expands_when_header_is_clicked(self):
        card = self.create_card({"Enabled": True})

        self.assertFalse(card.card.expandButton.isHidden())
        QTest.mouseClick(card.card, Qt.LeftButton)
        QApplication.processEvents()

        self.assertTrue(card.isExpand)
