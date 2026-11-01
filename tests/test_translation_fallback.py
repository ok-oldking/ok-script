import unittest
import string
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from ok import App, HeadlessApp

I18N_DIR = Path(__file__).resolve().parents[1] / 'ok' / 'ui' / 'qt' / 'i18n'


def _locales():
    return sorted(path.stem for path in I18N_DIR.glob('*.ts'))


class TestTranslationFallback(unittest.TestCase):
    def test_error_templates_are_available_in_the_contexts_used_at_runtime(self):
        from PySide6.QtCore import QTranslator
        from ok.ui.qt import resources

        sources = {
            'app': [
                'Cannot start: the app is controlled by {owner}',
                'Cannot start {name}: the app is controlled by {owner}',
                'Start failed: {error}',
                'Start game timeout!',
                'Start game failed, please start game first',
                'Game path does not exist, Please open game manually!',
                'No game selected!',
                '{} is not connected, please select the game window.',
                'Selected capture method is not supported by the game or your system!',
                'Emulator is not connected, start the emulator first!',
                "Window is minimized or out of screen, and don't use full-screen exclusive mode!",
                'Capture failed, please check game window',
                "Image resource load failed, please try install again.(Don't put the app in Downloads folder)",
                'PC version requires admin privileges, Please restart this app with admin privileges!',
                'NPU inferring Error, you might need to update the Intel NPU driver!',
                'Windows Graphics Capture is busy',
                'Windows Graphics Capture is not supported on this system.',
                'Paused because browser exited',
                'Export failed',
            ],
            'JobControls': ['The app is controlled by {owner}', 'Failed after {seconds}s'],
            'DebugTab': ['The app is controlled by {owner}'],
            'StartTab': ['Please Start First'],
            'StartButton': ['Error', 'No Task to Run, Please Enable Task First!'],
            'MainWindow': ['Import failed: {error}'],
            'EditTaskTab': [
                'Error deleting task: {error}', 'Error creating task: {error}', 'Error copying task: {error}',
                'Could not find source file for {}', 'Failed to read source file: {}',
            ],
            'TemplateInputDialog': ["Parameter '{param_name}' is required!"],
            'TemplateTab': [
                'Screenshot failed: {e}', 'Save failed: {e}', 'Delete failed: {e}',
                'Could not write screenshot to {path}',
            ],
            'PluginTab': [
                'The release archive belongs to a different plugin',
                'The release archive is not a newer plugin version',
            ],
        }
        formatter = string.Formatter()
        for locale in _locales():
            tree = ET.parse(I18N_DIR / f'{locale}.ts')
            catalog = {(c.findtext('name'), m.findtext('source')): m.find('translation')
                       for c in tree.findall('context') for m in c.findall('message')}
            translator = QTranslator()
            # English is the source language and is not embedded in qt.qrc.
            if locale != 'en_US':
                self.assertTrue(translator.load(f':/i18n/{locale}.qm'))
            for context, messages in sources.items():
                for source in messages:
                    with self.subTest(locale=locale, context=context, source=source):
                        entry = catalog[(context, source)]
                        self.assertNotIn(entry.get('type'), ('unfinished', 'vanished', 'obsolete'))
                        translated = entry.text
                        self.assertTrue(translated)
                        if locale != 'en_US':
                            self.assertEqual(translated, translator.translate(context, source))
                            if not (locale == 'es_ES' and source == 'Error'):
                                self.assertNotEqual(source, translated)
                        self.assertEqual(
                            sorted(field for _, field, _, _ in formatter.parse(source) if field is not None),
                            sorted(field for _, field, _, _ in formatter.parse(translated) if field is not None),
                        )
                        translated.format('Game', owner='MCP', name='Task', error='details', seconds='1.25',
                                          param_name='target', e='details', path='C:/screenshots/test.png')

    def test_start_failure_translates_before_formatting_exception_details(self):
        from PySide6.QtCore import QCoreApplication, QTranslator
        from ok.ui.qt import resources
        from ok.core.start_controller import StartController
        from unittest.mock import Mock, patch

        application = QCoreApplication.instance() or QCoreApplication([])
        facade = SimpleNamespace(po_translation=SimpleNamespace(gettext=lambda key: key), to_translate=None)
        facade.tr = lambda key: App.tr(facade, key)
        controller = object.__new__(StartController)
        controller.start_timeout = 60
        executor = SimpleNamespace(exclusive_owner=None, onetime_tasks=[])
        event = Mock()
        source = 'Start failed: {error}'
        for locale in _locales():
            if locale == 'en_US':
                continue
            translator = QTranslator()
            self.assertTrue(translator.load(f':/i18n/{locale}.qm'))
            application.installTranslator(translator)
            try:
                with self.subTest(locale=locale), \
                        patch('ok.core.start_controller.og', SimpleNamespace(app=facade, executor=executor)), \
                        patch('ok.core.start_controller.communicate', SimpleNamespace(starting_emulator=event)):
                    self.assertFalse(controller._do_start(task=0))
                    event.emit.assert_called_with(
                        True, translator.translate('app', source).format(error='list index out of range'), 0)
            finally:
                application.removeTranslator(translator)

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
        for locale in _locales():
            translator = QTranslator()
            if locale != 'en_US':
                self.assertTrue(translator.load(f':/i18n/{locale}.qm'))
                application.installTranslator(translator)
            try:
                with patch('ok.core.start_controller.og', SimpleNamespace(app=facade)):
                    for source in sources:
                        with self.subTest(locale=locale, source=source):
                            translated = controller.tr(source)
                            translated.format(**values)
                            if locale == 'en_US':
                                self.assertEqual(source, translated)
                            else:
                                self.assertNotEqual(source, translated)
            finally:
                application.removeTranslator(translator)

    def test_wgc_descriptions_are_translated(self):
        from PySide6.QtCore import QTranslator
        from ok.ui.qt import resources
        from ok.core.capture_labels import capture_method_label

        self.assertEqual('WGC - Fast, support HDR (not AutoHDR)', capture_method_label('WGC'))
        self.assertEqual('WGC_HDR - Only use when using AutoHDR (Not Recommended)',
                         capture_method_label('WGC_HDR'))
        for locale in _locales():
            if locale == 'en_US':
                continue
            translator = QTranslator()
            self.assertTrue(translator.load(f':/i18n/{locale}.qm'))
            for method in ('WGC', 'WGC_HDR'):
                with self.subTest(locale=locale, method=method):
                    source = capture_method_label(method)
                    translated = translator.translate('SelectCaptureListView', source)
                    self.assertTrue(translated.startswith(method + ' - '))
                    self.assertNotEqual(source, translated)

    def test_auto_hdr_error_is_translated_in_bundled_qt_catalogs(self):
        from PySide6.QtCore import QTranslator
        from ok.ui.qt import resources  # Register the bundled translation resources.

        source = 'Auto HDR is enabled, tasks might not work correctly!'
        for locale in _locales():
            with self.subTest(locale=locale):
                tree = ET.parse(I18N_DIR / f'{locale}.ts')
                context = next(c for c in tree.findall('context') if c.findtext('name') == 'StartController')
                expected = next(m.findtext('translation') for m in context.findall('message')
                                if m.findtext('source') == source)
                self.assertTrue(expected)
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
