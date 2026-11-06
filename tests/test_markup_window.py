import os
import tempfile
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtGui import QColor, QIcon, QImage
from PySide6.QtWidgets import QApplication

from ok import og


class TestMarkUpWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_cwd = os.getcwd()
        self.old_app = getattr(og, "app", None)
        os.chdir(self.folder.name)
        og.app = SimpleNamespace(icon=QIcon())
        from ok.ui.qt.tasks.TemplateTab import ensure_template_folder, save_coco
        folder = ensure_template_folder()
        self.images = []
        for name in ("a.png", "b.png"):
            image = QImage(200, 100, QImage.Format.Format_RGB32)
            image.fill(QColor("navy"))
            path = os.path.join(folder, name)
            image.save(path)
            self.images.append(path)
        save_coco({
            'images': [{'id': 1, 'file_name': 'a.png', 'width': 200, 'height': 100}],
            'annotations': [{'id': 1, 'image_id': 1, 'category_id': 1, 'bbox': [10, 20, 30, 40], 'area': 1200,
                             'iscrowd': 0}],
            'categories': [{'id': 1, 'name': 'boss', 'supercategory': ''}],
        })

    def tearDown(self):
        og.app = self.old_app
        os.chdir(self.old_cwd)
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.folder.cleanup()

    def make_window(self):
        from ok.ui.qt.tasks.MarkUpWindow import MarkUpWindow
        window = MarkUpWindow(self.images[0], self.images)
        self.addCleanup(window.deleteLater)
        return window

    def test_feature_list_follows_the_image_and_selection(self):
        window = self.make_window()
        self.assertEqual(1, window.feature_list.count())
        self.assertIn("boss", window.feature_list.item(0).text())
        self.assertTrue(window.empty_features_label.isHidden())
        self.assertEqual("1 / 2", window.position_label.text().split("·")[-1].strip())

        window.feature_list.setCurrentRow(0)
        self.assertEqual(0, window.canvas.selected_ann_index)
        window.canvas.selection_changed.emit(-1)
        self.assertEqual(-1, window.feature_list.currentRow())

        window.next_image()
        self.assertEqual(0, window.feature_list.count())
        self.assertFalse(window.empty_features_label.isHidden())
        self.assertFalse(window.right_btn.isEnabled())

    def test_copied_annotation_is_saved_and_listed(self):
        window = self.make_window()
        window.canvas.selected_ann_index = 0
        window.canvas.copy_selected()
        self.assertEqual(2, window.feature_list.count())
        names = {cat['name'] for cat in window.coco_data['categories']}
        self.assertEqual({"boss", "boss_copy"}, names)

    def test_bbox_dialog_requires_a_unique_name(self):
        from ok.ui.qt.tasks.MarkUpWindow import BBoxDialog
        window = self.make_window()
        dialog = BBoxDialog(window.canvas, "", 1, 2, 3, 4, existing_categories={"boss": "other.png"})
        self.addCleanup(dialog.deleteLater)
        self.assertFalse(dialog.ok_button.isEnabled())
        dialog.category_input.setText("boss")
        self.assertFalse(dialog.ok_button.isEnabled())
        self.assertIn("other.png", dialog.cat_error_label.text())
        dialog.category_input.setText("enemy")
        self.assertTrue(dialog.ok_button.isEnabled())
        self.assertEqual(("enemy", 1, 2, 3, 4), dialog.get_values())


if __name__ == "__main__":
    unittest.main()
