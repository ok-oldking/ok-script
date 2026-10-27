import os
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ok import Config, og
from ok.ui.qt.common.design_system import DesignToken
from ok.ui.qt.tasks.MarkUpWindow import MarkUpWindow
from ok.ui.qt.tasks.TemplateTab import (ImageCard, TemplateTab,
                                      get_categories_by_filename,
                                      get_next_image_name)


class TestTemplateTabCardCollection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        self.old_config_folder = Config.config_folder
        self.old_app = getattr(og, 'app', None)
        os.chdir(self.temp_dir.name)
        Config.config_folder = self.temp_dir.name
        og.app = SimpleNamespace(icon=QIcon())
        self.tab = TemplateTab(Config('template_tab_test', {}))
        self.tab._grid_loading = False

    def tearDown(self):
        self.tab.close()
        self.tab.deleteLater()
        QApplication.processEvents()
        Config.config_folder = self.old_config_folder
        og.app = self.old_app
        os.chdir(self.old_cwd)
        self.temp_dir.cleanup()

    def _add_item(self, name, categories=None):
        path = os.path.join(self.temp_dir.name, name)
        self.tab._create_image_item(path, categories or [])
        return path

    def test_uses_standard_page_layout(self):
        layout = self.tab.layout()
        margins = layout.contentsMargins()
        self.assertEqual(
            (margins.left(), margins.top(), margins.right(), margins.bottom()),
            (DesignToken.PAGE_MARGIN,) * 4,
        )
        self.assertEqual(layout.spacing(), DesignToken.PAGE_SPACING)

    def test_export_dialog_defaults_to_split_and_switches_to_compress(self):
        from qfluentwidgets import MessageBoxBase, RadioButton

        for debug in (False, True):
            for split in (True, False):
                with self.subTest(debug=debug, split=split):
                    og.app.debug = debug
                    observed = []

                    def accept_dialog(dialog):
                        buttons = {button.text(): button for button in dialog.findChildren(RadioButton)}
                        self.assertTrue(buttons['Split(Recommend)'].isChecked())
                        destination = 'assets (standalone app)' if debug else 'ok_tasks/assets (custom scripts)'
                        self.assertTrue(buttons[destination].isChecked())
                        if not split:
                            buttons['Compress (obsolete)'].setChecked(True)
                            observed.append(buttons[destination].text())
                        return 1

                    executor = SimpleNamespace(feature_set=Mock())
                    with patch.object(MessageBoxBase, 'exec', accept_dialog), \
                            patch('ok.ui.qt.tasks.TemplateTab.os.path.exists', return_value=True), \
                            patch('ok.feature.FeatureSet.generate_templates') as generate, \
                            patch('ok.feature.FeatureSet.compress_copy_coco') as compress, \
                            patch('ok.ui.qt.util.Alert.alert_info'), \
                            patch('ok.ui.qt.util.Alert.alert_error') as error, \
                            patch.object(og, 'executor', executor):
                        self.tab.save_compressed()
                        chosen, unused = (generate, compress) if split else (compress, generate)
                        chosen.assert_called_once()
                        unused.assert_not_called()
                        folder = os.path.join('assets', 'templates') if split else 'assets'
                        expected = os.path.abspath(folder if debug else os.path.join('ok_tasks', folder))
                        self.assertEqual(expected, chosen.call_args.args[1])
                        executor.feature_set.process_data.assert_called_once()
                        error.assert_not_called()
                    if not split:
                        expected_label = 'assets (standalone app)' if debug else 'ok_tasks/assets (custom scripts)'
                        self.assertEqual([expected_label], observed)

    def test_search_reuses_cards_and_clears_hidden_selection(self):
        boss_path = self._add_item('boss.png', ['boss'])
        other_path = self._add_item('other.png', ['enemy'])
        boss_card = self.tab._cards_by_path[boss_path]

        self.tab.apply_filter()
        self.tab.selected_image = boss_path
        boss_card.set_selected(True)
        self.tab.search_box.setText('enemy')
        self.tab.apply_filter()

        self.assertEqual([other_path], self.tab._visible_image_paths)
        self.assertIs(boss_card, self.tab._cards_by_path[boss_path])
        self.assertTrue(boss_card.isHidden())
        self.assertFalse(boss_card.selected)
        self.assertIsNone(self.tab.selected_image)

    def test_annotation_categories_update_search_results_without_reloading_cards(self):
        image_path = self._add_item('image.png')
        card = self.tab._cards_by_path[image_path]
        self.tab.search_box.setText('boss')

        annotated_coco = {
            'images': [{'id': 1, 'file_name': 'image.png', 'width': 0, 'height': 0}],
            'annotations': [{'id': 1, 'image_id': 1, 'category_id': 1,
                             'bbox': [0, 0, 1, 1], 'area': 1, 'iscrowd': 0}],
            'categories': [{'id': 1, 'name': 'boss', 'supercategory': ''}]
        }
        self.tab.on_markup_closed([image_path], annotated_coco)

        self.assertEqual([image_path], self.tab._visible_image_paths)
        self.assertEqual('boss', card.features_label.text())

        self.tab.on_markup_closed([image_path], {
            'images': annotated_coco['images'], 'annotations': [], 'categories': []
        })

        self.assertEqual([], self.tab._visible_image_paths)
        self.assertIs(card, self.tab._cards_by_path[image_path])
        self.assertTrue(card.isHidden())

    def test_duplicate_filename_categories_are_merged_and_searchable(self):
        filename = 'A_Very_Long_Template_Filename_That_Has_Duplicate_Coco_Entries.png'
        image_path = self._add_item(filename)
        card = self.tab._cards_by_path[image_path]
        coco_data = {
            'images': [
                {'id': 1, 'file_name': f'images/{filename}', 'width': 0, 'height': 0},
                {'id': 2, 'file_name': filename.lower(), 'width': 0, 'height': 0},
            ],
            'annotations': [
                {'id': 1, 'image_id': 1, 'category_id': 1},
                {'id': 2, 'image_id': 2, 'category_id': 2},
            ],
            'categories': [
                {'id': 1, 'name': 'first_feature', 'supercategory': ''},
                {'id': 2, 'name': 'previously_missing_feature', 'supercategory': ''},
            ],
        }

        self.tab.on_markup_closed([image_path], coco_data)
        self.assertEqual('first_feature, previously_missing_feature', card.features_label.text())

        self.tab.search_box.setText('previously_missing_feature')
        self.tab.apply_filter()
        self.assertEqual([image_path], self.tab._visible_image_paths)

    def test_long_feature_and_file_names_are_not_clipped(self):
        card = ImageCard(
            os.path.join(
                self.temp_dir.name,
                'a_very_long_template_filename_that_wraps_onto_more_than_two_lines.png',
            ),
            features_text=', '.join(f'feature_{i}_with_a_long_name' for i in range(5)),
        )

        self.assertGreaterEqual(
            card.features_label.height(),
            card.features_label.sizeHint().height(),
        )
        self.assertGreaterEqual(
            card.name_label.height(),
            card.name_label.sizeHint().height(),
        )

    def test_removing_item_only_removes_its_card(self):
        first_path = self._add_item('first.png')
        second_path = self._add_item('second.png')
        second_card = self.tab._cards_by_path[second_path]
        self.tab.apply_filter()

        self.tab._remove_image_item(first_path)
        self.tab.apply_filter()

        self.assertNotIn(first_path, self.tab._cards_by_path)
        self.assertEqual([second_path], self.tab._visible_image_paths)
        self.assertIs(second_card, self.tab._cards_by_path[second_path])

    def test_markup_close_emits_the_editor_coco_data(self):
        editor = MarkUpWindow('', [])
        expected_coco = {'images': [], 'annotations': [], 'categories': []}
        editor.coco_data = expected_coco
        emitted = []
        editor.closed.connect(lambda paths, coco_data: emitted.append((paths, coco_data)))

        editor.close()

        self.assertEqual([([], expected_coco)], emitted)
        editor.deleteLater()

    def test_screenshot_captures_off_gui_thread_and_adds_item(self):
        release = threading.Event()
        capture_threads = []

        def get_frame(busy_wait=0):
            capture_threads.append(threading.current_thread())
            release.wait(5)
            return np.zeros((20, 20, 3), dtype=np.uint8)

        old_device_manager = getattr(og, 'device_manager', None)
        old_config = getattr(og, 'config', None)
        og.device_manager = SimpleNamespace(capture_method=SimpleNamespace(get_frame=get_frame))
        og.config = {}
        try:
            # A slow capture must not block the click handler.
            self.tab.take_screenshot()
            self.assertTrue(self.tab._capturing)
            self.assertFalse(self.tab.screenshot_btn.isEnabled())

            release.set()
            deadline = time.monotonic() + 5
            while self.tab._capturing and time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(.01)
        finally:
            release.set()
            og.device_manager = old_device_manager
            og.config = old_config

        self.assertFalse(self.tab._capturing)
        self.assertTrue(self.tab.screenshot_btn.isEnabled())
        self.assertIsNot(threading.main_thread(), capture_threads[0])
        self.assertEqual(1, len(self.tab._items_by_path))
        self.assertTrue(os.path.isfile(next(iter(self.tab._items_by_path))))

    def test_next_image_name_reuses_deleted_number_but_reserves_coco_entries(self):
        open(os.path.join(self.temp_dir.name, '0.png'), 'wb').close()
        coco_data = {
            'images': [{'id': 1, 'file_name': '2.png', 'width': 0, 'height': 0}],
            'annotations': [],
            'categories': []
        }

        self.assertEqual('1', get_next_image_name(self.temp_dir.name, coco_data))

    def test_category_index_preserves_category_order_and_deduplicates_annotations(self):
        coco_data = {
            'images': [
                {'id': 1, 'file_name': 'first.png', 'width': 0, 'height': 0},
                {'id': 2, 'file_name': 'second.png', 'width': 0, 'height': 0},
            ],
            'annotations': [
                {'id': 1, 'image_id': 1, 'category_id': 1},
                {'id': 2, 'image_id': 1, 'category_id': 2},
                {'id': 3, 'image_id': 1, 'category_id': 1},
            ],
            'categories': [
                {'id': 2, 'name': 'second', 'supercategory': ''},
                {'id': 1, 'name': 'first', 'supercategory': ''},
            ],
        }

        self.assertEqual(
            {'first.png': ['second', 'first'], 'second.png': []},
            get_categories_by_filename(coco_data),
        )


if __name__ == '__main__':
    unittest.main()
