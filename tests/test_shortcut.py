import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pyappify

from ok.util import shortcut


class TestShortcutNotification(unittest.TestCase):
    def test_notifies_with_the_changed_paths(self):
        paths = [r"C:\Start Menu\Demo.lnk", r"C:\Desktop\Demo.lnk"]
        with patch.object(pyappify, "create_shortcut", return_value=paths) as create, \
                patch("ok.core.events.communicate.notification") as notification:
            self.assertEqual(paths, shortcut.create_and_notify(True, False))
        create.assert_called_once_with(start_menu=True, desktop=False)
        notification.emit.assert_called_once_with(
            shortcut.SHORTCUTS_CHANGED_MESSAGE, shortcut.SHORTCUTS_CHANGED_TITLE, False, True, None,
            {"paths": ", ".join(paths)}, None)

    def test_up_to_date_shortcuts_do_not_notify(self):
        with patch.object(pyappify, "create_shortcut", return_value=[]), \
                patch("ok.core.events.communicate.notification") as notification:
            self.assertEqual([], shortcut.create_and_notify(True, True))
        notification.emit.assert_not_called()

    def test_failure_does_not_notify(self):
        with patch.object(pyappify, "create_shortcut", side_effect=OSError("boom")), \
                patch("ok.core.events.communicate.notification") as notification:
            self.assertEqual([], shortcut.create_and_notify(True, True))
        notification.emit.assert_not_called()

    def test_message_is_translated_with_its_placeholder(self):
        from PySide6.QtCore import QCoreApplication, QTranslator
        app = QCoreApplication.instance() or QCoreApplication([])
        translator = QTranslator()
        qm = os.path.join(os.path.dirname(shortcut.__file__), "..", "ui", "qt", "i18n", "zh_CN.qm")
        self.assertTrue(translator.load(os.path.abspath(qm)))
        app.installTranslator(translator)
        try:
            text = QCoreApplication.translate("app", shortcut.SHORTCUTS_CHANGED_MESSAGE)
            self.assertNotEqual(shortcut.SHORTCUTS_CHANGED_MESSAGE, text)
            self.assertIn("a.lnk", text.format(paths="a.lnk"))
        finally:
            app.removeTranslator(translator)


if __name__ == "__main__":
    unittest.main()
