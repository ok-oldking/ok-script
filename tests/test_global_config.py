import unittest
import tempfile
import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon

from ok import og
from ok.gui.tasks.ConfigItemFactory import config_widget
from ok.util.GlobalConfig import (
    APP_LAUNCHER_ACTION,
    APP_LAUNCHER_AUTO_START,
    APP_LAUNCHER_OPEN,
    APP_LAUNCHER_OPTION_NAME,
    APP_LAUNCHER_UPDATE_METHOD,
    KILL_LAUNCHER_AFTER_START,
    GlobalConfig,
    create_app_launcher_options,
    create_basic_options,
    register_app_launcher_options,
    register_basic_options,
)
from ok.util.config import Config, ConfigOption


class TestBasicOptions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_enable_blur_only_exists_when_blur_area_is_available(self):
        self.assertNotIn('Enable Blur', create_basic_options().default_config)
        options = create_basic_options(enable_blur=True)

        self.assertFalse(options.default_config['Enable Blur'])
        self.assertEqual('Inpaint', options.default_config['Blur Algorithm'])
        self.assertEqual(1, options.default_config['Blur Interval'])
        self.assertIn('OLED', options.config_description['Enable Blur'])
        self.assertEqual({True: ['Blur Algorithm', 'Blur Interval']},
                         options.config_type['Enable Blur']['sub_configs'])
        self.assertEqual(['Blur', 'Inpaint'], options.config_type['Blur Algorithm']['options'])
        self.assertEqual(0, options.config_type['Blur Interval']['min'])

    def test_config_option_show_at_tab_defaults_to_false(self):
        option = ConfigOption('Custom Options')

        self.assertFalse(option.show_at_tab)

    def test_config_option_can_request_dedicated_tab(self):
        option = ConfigOption('Custom Options', show_at_tab=True)

        self.assertTrue(option.show_at_tab)

    def test_loading_valid_config_does_not_rewrite_it_per_key(self):
        current = {f'key_{index}': index for index in range(20)}

        with patch('ok.util.config.read_json_file', return_value=current), \
                patch.object(Config, 'save_file') as save_file:
            config = Config('Existing Config', dict(current))

        self.assertEqual(current, config)
        save_file.assert_not_called()

    def test_config_migration_is_saved_once(self):
        current = {'kept': 1, 'removed': True}
        defaults = {'kept': 1, 'added': 2}

        with patch('ok.util.config.read_json_file', return_value=current), \
                patch.object(Config, 'save_file') as save_file:
            config = Config('Migrated Config', defaults)

        self.assertEqual(defaults, config)
        save_file.assert_called_once_with()

    def test_global_config_tab_renders_options_without_card_container(self):
        from ok.gui.settings.GlobalConfigTab import GlobalConfigTab

        original_app = getattr(og, 'app', None)
        original_folder = Config.config_folder
        try:
            with tempfile.TemporaryDirectory() as folder:
                Config.config_folder = folder
                og.app = SimpleNamespace(tr=lambda text: text)
                option = ConfigOption(
                    'Tab Options',
                    {'Enabled': True},
                    description='Configure tab options',
                    show_at_tab=True
                )
                config = Config(option.name, option.default_config)

                tab = GlobalConfigTab(config, option)

                self.assertTrue(tab.has_key('Enabled'))
                self.assertEqual('Tab Options', tab.titleLabel.text())
                self.assertEqual('viewTitleLabel', tab.titleLabel.objectName())
                self.assertEqual('Configure tab options', tab.descriptionLabel.text())
                self.assertEqual('contentLabel', tab.descriptionLabel.objectName())
                self.assertEqual('configContentFrame', tab.contentFrame.objectName())
                self.assertIsNot(tab.viewLayout, tab.vBoxLayout)
                self.assertFalse(hasattr(tab, 'card'))
                tab.deleteLater()
        finally:
            og.app = original_app
            Config.config_folder = original_folder

    def test_blur_option_is_added_to_app_defined_basic_options(self):
        original_folder = Config.config_folder
        try:
            with tempfile.TemporaryDirectory() as folder:
                Config.config_folder = folder
                custom = ConfigOption('Basic Options', {'Custom Setting': True})
                global_config = GlobalConfig([custom])

                config = register_basic_options(global_config, enable_blur=True)

                self.assertTrue(config['Custom Setting'])
                self.assertFalse(config['Enable Blur'])
                self.assertEqual('Inpaint', config['Blur Algorithm'])
                self.assertEqual(1, config['Blur Interval'])
                self.assertIn('Enable Blur', custom.config_description)
                self.assertIn('Blur Algorithm', custom.config_type)
        finally:
            Config.config_folder = original_folder

    def test_blur_interval_widget_accepts_zero(self):
        original_app = getattr(og, 'app', None)
        original_folder = Config.config_folder
        try:
            with tempfile.TemporaryDirectory() as folder:
                Config.config_folder = folder
                options = create_basic_options(enable_blur=True)
                config = Config(options.name, options.default_config)
                og.app = SimpleNamespace(tr=lambda text: text)

                config['Blur Interval'] = 1
                widget = config_widget(
                    options.config_type, options.config_description, config, 'Blur Interval', 1, None)

                self.assertEqual(0, widget.spin_box.minimum())
                widget.spin_box.setValue(0)
                self.assertEqual(0, config['Blur Interval'])
                widget.deleteLater()
        finally:
            og.app = original_app
            Config.config_folder = original_folder

    def test_old_pyappify_does_not_add_app_launcher_options(self):
        global_config = GlobalConfig(None)

        result = register_app_launcher_options(global_config, SimpleNamespace())

        self.assertIsNone(result)
        self.assertNotIn(APP_LAUNCHER_OPTION_NAME, global_config.configs)

    def test_app_launcher_options_require_an_existing_config_file(self):
        with tempfile.TemporaryDirectory() as folder:
            pyappify_module = SimpleNamespace(
                get_app_json_path=lambda: os.path.join(folder, 'missing-app.json'),
                get_app_config=lambda: {'auto_start': False, 'update_method': 'AUTO_UPDATE'},
                update_app_config=lambda **changes: changes,
            )

            self.assertIsNone(create_app_launcher_options(pyappify_module))

    def test_app_launcher_options_update_pyappify_config(self):
        with tempfile.TemporaryDirectory() as folder:
            config_path = os.path.join(folder, 'app.json')
            with open(config_path, 'w', encoding='utf-8') as config_file:
                config_file.write('{}')
            launcher_config = {'auto_start': False, 'update_method': 'AUTO_UPDATE'}
            updates = []
            launcher_opened = []

            def update_app_config(**changes):
                launcher_config.update(changes)
                updates.append(changes)
                return dict(launcher_config)

            pyappify_module = SimpleNamespace(
                get_app_json_path=lambda: config_path,
                get_app_config=lambda: dict(launcher_config),
                update_app_config=update_app_config,
                show_pyappify=lambda: launcher_opened.append(True),
            )
            global_config = GlobalConfig(None)
            basic_option = create_basic_options()
            basic_config = Config(basic_option.name, basic_option.default_config, folder=folder)
            global_config.register_config(basic_option, basic_config)

            config = register_app_launcher_options(global_config, pyappify_module)
            option = global_config.config_options[APP_LAUNCHER_OPTION_NAME]

            self.assertFalse(option.show_at_tab)
            self.assertFalse(option.default_config)
            self.assertEqual(FluentIcon.APPLICATION, option.icon)
            launcher_button = option.config_type[APP_LAUNCHER_ACTION]
            self.assertEqual(APP_LAUNCHER_OPEN, launcher_button['text'])
            self.assertEqual(FluentIcon.UPDATE, launcher_button['icon'])
            launcher_button['callback']()
            self.assertEqual([True], launcher_opened)
            self.assertFalse(config[APP_LAUNCHER_AUTO_START])
            self.assertEqual('Automatic Update(Release Only)', config[APP_LAUNCHER_UPDATE_METHOD])
            self.assertTrue(config[KILL_LAUNCHER_AFTER_START])
            self.assertTrue(basic_option.config_type[KILL_LAUNCHER_AFTER_START]['hidden'])

            config[APP_LAUNCHER_AUTO_START] = True
            config[APP_LAUNCHER_UPDATE_METHOD] = 'Automatic Update (Pre-release)'
            config[KILL_LAUNCHER_AFTER_START] = False

            self.assertEqual(
                [
                    {'auto_start': True},
                    {'update_method': 'AUTO_UPDATE_PRE_RELEASE'},
                ],
                updates,
            )
            self.assertTrue(config[APP_LAUNCHER_AUTO_START])
            self.assertEqual('Automatic Update (Pre-release)', config[APP_LAUNCHER_UPDATE_METHOD])
            self.assertFalse(config[KILL_LAUNCHER_AFTER_START])
            self.assertFalse(basic_config[KILL_LAUNCHER_AFTER_START])

            config.reset_to_default()

            self.assertEqual(
                {'auto_start': False, 'update_method': 'AUTO_UPDATE'},
                updates[-1],
            )
            self.assertFalse(config[APP_LAUNCHER_AUTO_START])
            self.assertEqual('Automatic Update(Release Only)', config[APP_LAUNCHER_UPDATE_METHOD])
            self.assertFalse(basic_config[KILL_LAUNCHER_AFTER_START])

            original_app = getattr(og, 'app', None)
            original_config = getattr(og, 'config', None)
            try:
                from ok.gui.settings.GlobalConfigCard import GlobalConfigCard

                og.app = SimpleNamespace(tr=lambda text: text)
                og.config = {'gui_title': 'Demo App'}
                launcher_card = GlobalConfigCard(config, option)
                basic_card = GlobalConfigCard(basic_config, basic_option)

                self.assertIsNone(launcher_card.reset_config)
                self.assertIn(KILL_LAUNCHER_AFTER_START, launcher_card.config_widget_by_key)
                self.assertNotIn(KILL_LAUNCHER_AFTER_START, basic_card.config_widget_by_key)
                self.assertEqual(
                    'Auto Start Demo App',
                    launcher_card.config_widget_by_key[APP_LAUNCHER_AUTO_START].title.text(),
                )
                launcher_card.deleteLater()
                basic_card.deleteLater()
            finally:
                og.app = original_app
                og.config = original_config
