import unittest
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from ok import App, HeadlessApp


class TestTranslationFallback(unittest.TestCase):
    def test_capture_descriptions_and_startup_warnings_use_app_translation_context(self):
        from PySide6.QtCore import QCoreApplication, QTranslator
        from ok.ui.qt import resources
        from ok.core.start_controller import StartController
        from unittest.mock import patch

        application = QCoreApplication.instance() or QCoreApplication([])
        facade = SimpleNamespace(
            po_translation=SimpleNamespace(gettext=lambda key: key),
            to_translate=None,
        )
        facade.tr = lambda key: App.tr(facade, key)
        controller = object.__new__(StartController)
        root = Path(__file__).resolve().parents[1]
        catalogs = json.loads((root / 'web_src/src/i18n/catalogs.json').read_text(encoding='utf-8'))
        sources = [
            'Fast, support HDR (not AutoHDR)',
            'Only use when using AutoHDR (Not Recommended)',
            'GPU Driver Warning',
            '{vendor} {feature} is enabled and may cause malfunctions!',
            'Try using Alt+F3 to turn it off.',
            'Resolution {resolution} check failed, some tasks might not work correctly!',
            ', the supported ratio is {supported_ratio}',
            ', the supported min resolution is {min_size}',
        ]
        values = dict(vendor='NVIDIA', feature='RTX HDR', resolution='5120x2160',
                      supported_ratio='16:9', min_size='1280x720')
        for locale, catalog in catalogs.items():
            translator = QTranslator()
            if locale != 'en_US':
                self.assertTrue(translator.load(f':/i18n/{locale}.qm'))
                application.installTranslator(translator)
            try:
                with patch('ok.core.start_controller.og', SimpleNamespace(app=facade)):
                    for source in sources:
                        with self.subTest(locale=locale, source=source):
                            translated = controller.tr(source)
                            self.assertEqual(catalog[source], translated)
                            self.assertEqual(catalog[source].format(**values), translated.format(**values))
                            if locale != 'en_US':
                                self.assertNotEqual(source, translated)
            finally:
                application.removeTranslator(translator)

    def test_wgc_descriptions_are_available_in_qt_and_web(self):
        from PySide6.QtCore import QTranslator
        from ok.ui.qt import resources
        from ok.core.capture_labels import capture_method_label

        root = Path(__file__).resolve().parents[1]
        catalogs = json.loads((root / 'web_src/src/i18n/catalogs.json').read_text(encoding='utf-8'))
        self.assertEqual('WGC - Fast, support HDR (not AutoHDR)', capture_method_label('WGC'))
        self.assertEqual('WGC_HDR - Only use when using AutoHDR (Not Recommended)',
                         capture_method_label('WGC_HDR'))
        for locale, catalog in catalogs.items():
            for method in ('WGC', 'WGC_HDR'):
                with self.subTest(locale=locale, method=method):
                    source = capture_method_label(method)
                    self.assertTrue(catalog[source].startswith(method + ' - '))
                    if locale != 'en_US':
                        translator = QTranslator()
                        self.assertTrue(translator.load(f':/i18n/{locale}.qm'))
                        self.assertEqual(catalog[source], translator.translate('SelectCaptureListView', source))

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
