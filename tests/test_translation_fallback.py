import unittest
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from ok import App, HeadlessApp


class TestTranslationFallback(unittest.TestCase):
    def test_auto_hdr_error_is_translated_in_bundled_qt_and_web_catalogs(self):
        from PySide6.QtCore import QTranslator
        from ok.ui.qt import resources  # Register the bundled translation resources.

        source = 'Auto HDR is enabled, tasks might not work correctly!'
        root = Path(__file__).resolve().parents[1]
        catalogs = json.loads((root / 'web_src/src/i18n/catalogs.json').read_text(encoding='utf-8'))
        for locale in catalogs:
            with self.subTest(locale=locale):
                tree = ET.parse(root / f'ok/ui/qt/i18n/{locale}.ts')
                context = next(c for c in tree.findall('context') if c.findtext('name') == 'StartController')
                expected = next(m.findtext('translation') for m in context.findall('message')
                                if m.findtext('source') == source)
                self.assertEqual(expected, catalogs[locale][source])
                if locale != 'en_US':
                    translator = QTranslator()
                    self.assertTrue(translator.load(f':/i18n/{locale}.qm'))
                    self.assertEqual(expected, translator.translate('app', source))

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
