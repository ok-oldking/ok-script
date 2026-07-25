import os
import unittest
from unittest.mock import Mock, call, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qfluentwidgets import Theme

from ok.gui.MainWindow import MainWindow


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
        self._refresh_mica = Mock()


class _MicaHarness:
    _refresh_mica = MainWindow._refresh_mica

    def __init__(self, enabled):
        self.isMicaEffectEnabled = Mock(return_value=enabled)
        self.setMicaEffectEnabled = Mock()
        self.update = Mock()


class TestMainWindowSystemTheme(unittest.TestCase):
    def test_auto_mode_updates_resolved_theme_and_stylesheet(self):
        config = _FakeQConfig(Theme.AUTO, Theme.LIGHT, Theme.DARK)
        harness = _ThemeChangeHarness(accent_changed=True)

        with (
            patch("ok.gui.MainWindow.qconfig", config),
            patch("ok.gui.MainWindow.updateStyleSheet") as update_style_sheet,
            patch("ok.gui.MainWindow.QTimer.singleShot") as single_shot,
        ):
            harness._apply_system_theme_change()

        self.assertEqual(config.theme, Theme.DARK)
        config.themeChanged.emit.assert_called_once_with(Theme.AUTO)
        config.themeChangedFinished.emit.assert_called_once_with()
        update_style_sheet.assert_called_once_with()
        single_shot.assert_called_once_with(750, harness._refresh_mica)
        self.assertNotIn('system-theme', harness._theme_cooldowns)

    def test_fixed_mode_keeps_theme_but_applies_accent_change(self):
        config = _FakeQConfig(Theme.LIGHT, Theme.LIGHT, Theme.DARK)
        harness = _ThemeChangeHarness(accent_changed=True)

        with (
            patch("ok.gui.MainWindow.qconfig", config),
            patch("ok.gui.MainWindow.updateStyleSheet") as update_style_sheet,
            patch("ok.gui.MainWindow.QTimer.singleShot"),
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
            patch("ok.gui.MainWindow.qconfig", config),
            patch("ok.gui.MainWindow.updateStyleSheet") as update_style_sheet,
            patch("ok.gui.MainWindow.QTimer.singleShot"),
        ):
            harness._apply_system_theme_change()

        config.themeChanged.emit.assert_not_called()
        config.themeChangedFinished.emit.assert_called_once_with()
        update_style_sheet.assert_not_called()

    def test_refresh_mica_rebuilds_enabled_backdrop(self):
        harness = _MicaHarness(enabled=True)

        with patch("ok.gui.MainWindow.isDarkTheme", return_value=True):
            harness._refresh_mica()

        self.assertEqual(
            harness.setMicaEffectEnabled.call_args_list,
            [call(False), call(True)],
        )
        harness.update.assert_called_once_with()

    def test_refresh_mica_leaves_disabled_backdrop_unchanged(self):
        harness = _MicaHarness(enabled=False)

        harness._refresh_mica()

        harness.setMicaEffectEnabled.assert_not_called()
        harness.update.assert_not_called()


if __name__ == '__main__':
    unittest.main()
