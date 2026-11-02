import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qfluentwidgets import Theme

from ok.ui.qt.MainWindow import MainWindow


class _Signal:
    def __init__(self):
        self.emit = Mock()


class _FakeQConfig:
    def __init__(self, mode, theme, resolved_theme):
        self.themeMode = type("ThemeMode", (), {"value": mode})()
        self._theme = theme
        self.resolved_theme = resolved_theme
        self.themeChanged = _Signal()
        self.themeChangedFinished = _Signal()

    @property
    def theme(self):
        return self._theme

    @theme.setter
    def theme(self, value):
        self._theme = self.resolved_theme if value == Theme.AUTO else value


class _ThemeChangeHarness:
    _apply_system_theme_change = MainWindow._apply_system_theme_change

    def __init__(self, accent_changed):
        self._theme_cooldowns = {'system-theme'}
        self._sync_system_accent_color = Mock(return_value=accent_changed)
        self._sync_kit_theme = Mock()


class TestMainWindowSystemTheme(unittest.TestCase):
    def test_auto_mode_updates_resolved_theme_and_stylesheet(self):
        config = _FakeQConfig(Theme.AUTO, Theme.LIGHT, Theme.DARK)
        harness = _ThemeChangeHarness(accent_changed=True)

        with (
            patch("ok.ui.qt.MainWindow.qconfig", config),
            patch("ok.ui.qt.MainWindow.updateStyleSheet") as update_style_sheet,
        ):
            harness._apply_system_theme_change()

        self.assertEqual(config.theme, Theme.DARK)
        config.themeChanged.emit.assert_called_once_with(Theme.AUTO)
        config.themeChangedFinished.emit.assert_called_once_with()
        update_style_sheet.assert_called_once_with()
        harness._sync_kit_theme.assert_called_once_with()
        self.assertNotIn('system-theme', harness._theme_cooldowns)

    def test_fixed_mode_keeps_theme_but_applies_accent_change(self):
        config = _FakeQConfig(Theme.LIGHT, Theme.LIGHT, Theme.DARK)
        harness = _ThemeChangeHarness(accent_changed=True)

        with (
            patch("ok.ui.qt.MainWindow.qconfig", config),
            patch("ok.ui.qt.MainWindow.updateStyleSheet") as update_style_sheet,
            patch("ok.ui.qt.MainWindow.QTimer.singleShot"),
        ):
            harness._apply_system_theme_change()

        self.assertEqual(config.theme, Theme.LIGHT)
        config.themeChanged.emit.assert_not_called()
        config.themeChangedFinished.emit.assert_called_once_with()
        update_style_sheet.assert_called_once_with()

    def test_unchanged_theme_and_accent_skip_stylesheet_refresh(self):
        config = _FakeQConfig(Theme.AUTO, Theme.DARK, Theme.DARK)
        harness = _ThemeChangeHarness(accent_changed=False)

        with (
            patch("ok.ui.qt.MainWindow.qconfig", config),
            patch("ok.ui.qt.MainWindow.updateStyleSheet") as update_style_sheet,
            patch("ok.ui.qt.MainWindow.QTimer.singleShot"),
        ):
            harness._apply_system_theme_change()

        config.themeChanged.emit.assert_not_called()
        config.themeChangedFinished.emit.assert_called_once_with()
        update_style_sheet.assert_not_called()

    def test_kit_theme_follows_the_qfluent_theme_setting(self):
        from ok.ui.qt.kit import Theme as KitTheme
        from ok.ui.qt.kit import theme as kit_theme
        original = kit_theme.mode
        self.addCleanup(kit_theme.set_theme, original)
        harness = type("Harness", (), {"_sync_kit_theme": MainWindow._sync_kit_theme,
                                       "_system_accent": lambda self: None})()
        for mode, expected in ((Theme.DARK, KitTheme.DARK), (Theme.LIGHT, KitTheme.LIGHT),
                               (Theme.AUTO, KitTheme.AUTO)):
            with patch("ok.ui.qt.MainWindow.qconfig", _FakeQConfig(mode, mode, mode)):
                harness._sync_kit_theme()
            self.assertEqual(expected, kit_theme.mode)


if __name__ == '__main__':
    unittest.main()
