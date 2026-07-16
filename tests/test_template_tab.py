import os
import tempfile
import unittest
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ok import Config, og
from ok.gui.tasks.MarkUpWindow import MarkUpWindow
from ok.gui.tasks.TemplateTab import (TemplateTab, get_categories_by_filename,
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
