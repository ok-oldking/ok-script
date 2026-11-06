import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor

from ok.ui.qt.MainWindow import MainWindow
from ok.ui.qt.kit import Theme as KitTheme
from ok.ui.qt.kit import theme as kit_theme


class TestMainWindowSystemTheme(unittest.TestCase):
    def setUp(self):
        original_mode, original_accent = kit_theme.mode, kit_theme._accent
        original_backdrop = kit_theme.backdrop()
        self.addCleanup(kit_theme.set_backdrop, original_backdrop)
        self.addCleanup(lambda: (kit_theme.set_theme(original_mode), kit_theme.set_accent(original_accent)))

    def test_system_change_resyncs_and_clears_the_cooldown(self):
        harness = type("Harness", (), {"_apply_system_theme_change": MainWindow._apply_system_theme_change})()
        harness._theme_cooldowns = {'system-theme'}
        harness._sync_kit_theme = Mock()
        harness._apply_system_theme_change()
        harness._sync_kit_theme.assert_called_once_with()
        self.assertNotIn('system-theme', harness._theme_cooldowns)

    def test_kit_theme_follows_the_saved_mode_and_windows_accent(self):
        harness = type("Harness", (), {"_sync_kit_theme": MainWindow._sync_kit_theme,
                                       "_system_accent": lambda self: QColor("#123456")})()
        for mode, expected in (("dark", KitTheme.DARK), ("light", KitTheme.LIGHT), ("auto", KitTheme.AUTO)):
            with patch("ok.ui.qt.MainWindow.ui_config", Mock(theme_mode=mode, backdrop="acrylic")):
                harness._sync_kit_theme()
            self.assertEqual(expected, kit_theme.mode)
        self.assertEqual(QColor("#123456"), kit_theme._accent)


class TestUiConfig(unittest.TestCase):
    def test_reads_legacy_keys_and_saves_the_new_layout(self):
        import json
        import tempfile
        from ok.ui.qt.common.config import Language, UiConfig
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "ui_config.json")
            with open(path, "w", encoding="utf-8") as file:
                json.dump({"MainWindow": {"Language": "ja_JP"}, "QFluentWidgets": {"ThemeMode": "Dark"}}, file)
            config = UiConfig(path)
            self.assertEqual(Language.JAPANESE, config.language)
            self.assertEqual("dark", config.theme_mode)

            restart, themed = Mock(), Mock()
            config.language_changed.connect(restart)
            config.theme_changed.connect(themed)
            config.set_language(Language.ENGLISH)
            config.set_theme_mode("light")
            config.set_theme_mode("light")
            restart.assert_called_once_with()
            themed.assert_called_once_with()
            with open(path, encoding="utf-8") as file:
                self.assertEqual({"language": "en_US", "theme": "light", "backdrop": "acrylic"}, json.load(file))
            self.assertEqual("light", UiConfig(path).theme_mode)


if __name__ == '__main__':
    unittest.main()
