import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from ok import og
from ok.util.config import Config, ConfigOption


class FakeGlobalConfig:
    def __init__(self, entries):
        self.entries = entries

    def get_all_visible_configs(self):
        return list(self.entries)


class TestSettingsPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._og = {name: getattr(og, name, None) for name in ("app", "executor", "config")}
        self._folder = tempfile.TemporaryDirectory()
        self._config_folder = Config.config_folder
        Config.config_folder = self._folder.name
        og.app = SimpleNamespace(tr=lambda text: text)
        og.config = {"gui_title": "Demo"}
        basic = ConfigOption("Basic Options", {"Mute": True, "Interval": 3}, description="Basics")
        launcher = ConfigOption("App Launcher", {"Auto Start": False})
        tab_only = ConfigOption("Notifications", {"Sound": True}, show_at_tab=True)
        self.entries = [(option.name, Config(option.name, option.default_config), option)
                        for option in (basic, launcher, tab_only)]
        og.executor = SimpleNamespace(global_config=FakeGlobalConfig(self.entries))

    def tearDown(self):
        for name, value in self._og.items():
            setattr(og, name, value)
        Config.config_folder = self._config_folder
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self._folder.cleanup()

    def make_page(self):
        from ok.ui.qt.settings.settings_page import SettingsPage
        page = SettingsPage()
        page.resize(1200, 600)
        page.show()
        QApplication.processEvents()
        self.addCleanup(page.deleteLater)
        return page

    def test_sections_and_anchors(self):
        page = self.make_page()
        names = [section.option.name for section in page.sections]
        self.assertEqual(["App Launcher", "Basic Options"], names)
        self.assertEqual(["App Config", "App Launcher", "Basic Options"], [a.text() for a in page.anchors])
        self.assertTrue(page.anchors[0].isChecked())
        basic = page.sections[1]
        self.assertEqual("Basics", basic.description_label.text())
        self.assertFalse(basic.reset_button.isHidden())

    def test_sections_grow_with_the_window(self):
        page = self.make_page()
        narrow = page.sections[1].width()
        page.resize(1900, 600)
        QApplication.processEvents()
        self.assertGreater(page.sections[1].width(), narrow + 500)

    def test_goto_config_scrolls_to_its_section(self):
        page = self.make_page()
        page.goto_config("Interval")
        target = page.sections[1]
        bar = page.scroll.verticalScrollBar()
        self.assertEqual(min(bar.maximum(), max(0, target.y() - 8)), bar.value())

    def test_section_reset_restores_defaults(self):
        page = self.make_page()
        section = page.sections[1]
        editor = section.config_widget_by_key["Mute"]
        editor.switch_button.click()
        self.assertFalse(section.config["Mute"])
        section.reset_button.click()
        self.assertTrue(section.config["Mute"])
        self.assertTrue(editor.switch_button.isChecked())

    def test_grouped_section_renders_one_card_per_group(self):
        from ok.ui.qt.settings.config_section import ConfigSection
        option = ConfigOption(
            "Grouped", {"Mute": True, "Enable": False, "Level": 1, "Hidden": True, "Loose": 2},
            config_type={
                "Mute": {"group": "Game"},
                "Enable": {"group": "Extra", "sub_configs": {True: ["Level"]}},
                "Hidden": {"group": "Gone", "hidden": True},
            })
        config = Config(option.name, option.default_config)
        section = ConfigSection(config, option)
        self.addCleanup(section.deleteLater)
        # "Level" follows its parent's group, "Loose" lands in Other, all-hidden "Gone" is dropped.
        self.assertEqual(["Game", "Extra", "Other"], list(section.group_widgets))
        self.assertEqual({"Mute", "Enable", "Level", "Loose"}, set(section.config_widget_by_key))
        section.config_widget_by_key["Mute"].switch_button.click()
        section.reset_button.click()
        self.assertTrue(section.config_widget_by_key["Mute"].switch_button.isChecked())

    def test_grouped_option_gets_a_nav_entry_per_group(self):
        grouped = ConfigOption("Basic Options", {"Mute": True, "Interval": 3, "Hidden": 1},
                               config_type={"Mute": {"group": "Game"}, "Interval": {"group": "Tasks"},
                                            "Hidden": {"group": "Gone", "hidden": True}})
        self.entries[0] = (grouped.name, Config(grouped.name, grouped.default_config), grouped)
        page = self.make_page()
        self.assertEqual(["App Config", "App Launcher", "Game", "Tasks"], [a.text() for a in page.anchors])
        game, tasks = page.sections[1], page.sections[2]
        self.assertEqual({"Mute"}, set(game.config_widget_by_key))
        page.goto_config("Interval")
        bar = page.scroll.verticalScrollBar()
        self.assertEqual(min(bar.maximum(), max(0, tasks.y() - 8)), bar.value())
        # Each group's Reset restores only its own keys.
        game.config["Mute"] = False
        game.config["Interval"] = 9
        game.reset_button.click()
        self.assertTrue(game.config["Mute"])
        self.assertEqual(9, game.config["Interval"])

    def test_basic_options_are_grouped_without_directml(self):
        from ok.ui.qt.settings.config_section import ConfigSection
        from ok.util.GlobalConfig import GlobalConfig, register_basic_options
        global_config = GlobalConfig([])
        config = register_basic_options(global_config, enable_blur=True)
        self.assertNotIn("Use DirectML", config)
        section = ConfigSection(config, global_config.config_options["Basic Options"])
        self.addCleanup(section.deleteLater)
        self.assertEqual(["Game", "Tasks", "Application"], list(section.group_widgets)[:3])
        self.assertIn("Blur", section.group_widgets)
        self.assertNotIn("Other", section.group_widgets)

    def test_theme_tabs_change_the_theme_setting(self):
        from ok.ui.qt.common.config import cfg
        page = self.make_page()
        target = "dark" if cfg.theme_mode != "dark" else "light"
        with patch.object(cfg, "set_theme_mode") as set_theme_mode:
            page.theme_tabs.set_current(target)
            set_theme_mode.assert_called_once_with(target)

    def test_language_list_matches_the_enum(self):
        from ok.ui.qt.common.config import Language
        page = self.make_page()
        self.assertEqual(len(list(Language)), page.language_combo.count())


if __name__ == "__main__":
    unittest.main()
