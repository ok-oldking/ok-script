import unittest
import tempfile
import os
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from ok import og
from ok.gui.tasks.ConfigItemFactory import config_widget
from ok.util.GlobalConfig import GlobalConfig, create_basic_options, register_basic_options
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
