import unittest
import tempfile

from ok.util.GlobalConfig import GlobalConfig, create_basic_options, register_basic_options
from ok.util.config import Config, ConfigOption


class TestBasicOptions(unittest.TestCase):
    def test_enable_blur_only_exists_when_blur_area_is_available(self):
        self.assertNotIn('Enable Blur', create_basic_options().default_config)
        options = create_basic_options(enable_blur=True)

        self.assertFalse(options.default_config['Enable Blur'])
        self.assertEqual('Inpaint', options.default_config['Blur Algorithm'])
        self.assertIn('OLED', options.config_description['Enable Blur'])
        self.assertEqual({True: ['Blur Algorithm']},
                         options.config_type['Enable Blur']['sub_configs'])
        self.assertEqual(['Blur', 'Inpaint'], options.config_type['Blur Algorithm']['options'])

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
                self.assertIn('Enable Blur', custom.config_description)
                self.assertIn('Blur Algorithm', custom.config_type)
        finally:
            Config.config_folder = original_folder
