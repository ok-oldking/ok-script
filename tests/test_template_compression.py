import json
import os
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from ok.feature.FeatureSet import compress_copy_coco


class TestTemplateCompression(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.target = self.root / 'assets'
        self.data = {'images': [], 'annotations': [], 'categories': [
            {'id': 1, 'name': 'feature', 'supercategory': ''},
        ]}

    def add_image(self, image_id, size=(20, 20), bbox=(1, 1, 5, 5)):
        width, height = size
        filename = f'{image_id}.png'
        cv2.imwrite(str(self.source / filename),
                    np.full((height, width, 3), image_id, dtype=np.uint8))
        self.data['images'].append({'id': image_id, 'file_name': filename,
                                    'width': width, 'height': height})
        self.data['annotations'].append({
            'id': image_id, 'image_id': image_id, 'category_id': 1,
            'bbox': list(bbox), 'area': bbox[2] * bbox[3], 'iscrowd': 0,
        })

    def save(self, target=None):
        source_json = self.source / 'coco_annotations.json'
        source_json.write_text(json.dumps(self.data), encoding='utf-8')
        output = Path(compress_copy_coco(str(source_json), str(target or self.target), str(self.source)))
        data = json.loads(output.read_text())
        return {image['id']: image['file_name'] for image in data['images']}

    def snapshot(self):
        return {path.name: path.read_bytes() for path in (self.target / 'images').glob('*.png')}

    def test_added_page_preserves_other_resolution_filenames_and_pixels(self):
        self.add_image(1)
        self.add_image(2, size=(30, 30))
        original = self.save()
        pixels = self.snapshot()
        self.add_image(3)
        updated = self.save()
        self.assertEqual(original, {key: updated[key] for key in original})
        self.assertEqual('images/2.png', updated[3])
        for filename, content in pixels.items():
            self.assertEqual(content, self.snapshot()[filename])
        first_save = self.snapshot()
        self.assertEqual(updated, self.save())
        self.assertEqual(first_save, self.snapshot())

    def test_fresh_exports_ignore_timestamps_and_annotation_order(self):
        self.add_image(1)
        self.add_image(2)
        original = self.save()
        pixels = self.snapshot()
        self.data['annotations'].reverse()
        self.data['images'].reverse()
        os.utime(self.source / '1.png', (2000000000, 2000000000))
        os.utime(self.source / '2.png', (1000000000, 1000000000))
        other = self.root / 'other'
        self.assertEqual(original, self.save(other))
        self.assertEqual(pixels, {path.name: path.read_bytes() for path in (other / 'images').glob('*.png')})

    def test_new_nonoverlapping_image_reuses_page(self):
        self.add_image(1)
        original = self.save()
        self.add_image(2, bbox=(10, 10, 5, 5))
        updated = self.save()
        self.assertEqual(original[1], updated[1])
        self.assertEqual(updated[1], updated[2])
        canvas = cv2.imread(str(self.target / updated[2]))
        np.testing.assert_array_equal(canvas[1:6, 1:6], np.full((5, 5, 3), 1))
        np.testing.assert_array_equal(canvas[10:15, 10:15], np.full((5, 5, 3), 2))

    def test_conflicting_edit_splits_page_and_deletion_cleans_stale_pages(self):
        self.add_image(1)
        self.add_image(2, bbox=(10, 10, 5, 5))
        self.add_image(3, size=(30, 30))
        original = self.save()
        self.data['annotations'][1]['bbox'] = [1, 1, 5, 5]
        updated = self.save()
        self.assertEqual(original[1], updated[1])
        self.assertEqual(original[3], updated[3])
        self.assertNotEqual(updated[1], updated[2])
        self.data['images'] = [image for image in self.data['images'] if image['id'] != 2]
        self.data['annotations'] = [ann for ann in self.data['annotations'] if ann['image_id'] != 2]
        self.assertEqual({1: updated[1], 3: updated[3]}, self.save())
        self.assertFalse((self.target / updated[2]).exists())


if __name__ == '__main__':
    unittest.main()
