import unittest
from types import SimpleNamespace

from ok import App, HeadlessApp


class TestTranslationFallback(unittest.TestCase):
    def test_empty_custom_translation_returns_original_text(self):
        source = 'Original task text'
        facade = SimpleNamespace(
            po_translation=SimpleNamespace(gettext=lambda key: ''),
            to_translate=None,
        )

        for app_type in (App, HeadlessApp):
            with self.subTest(app_type=app_type.__name__):
                self.assertEqual(source, app_type.tr(facade, source))

    def test_non_empty_custom_translation_is_preserved(self):
        facade = SimpleNamespace(
            po_translation=SimpleNamespace(gettext=lambda key: 'Translated task text'),
            to_translate=None,
        )

        for app_type in (App, HeadlessApp):
            with self.subTest(app_type=app_type.__name__):
                self.assertEqual('Translated task text', app_type.tr(facade, 'Original task text'))


if __name__ == '__main__':
    unittest.main()
