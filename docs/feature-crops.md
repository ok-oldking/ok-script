# Exported feature crops

The Template tab's Save dialog defaults to **Split(Recommend)**. It calls
`generate_templates` and writes one crop-sized PNG per feature.

| Dialog destination | Split output folder |
| --- | --- |
| `assets` | `assets/templates` |
| `ok_tasks/assets` | `ok_tasks/assets/templates` |

The **Compress (obsolete)** option and old compression APIs are deprecated.
Use Split for new exports. Existing COCO assets remain readable.

Keep the original screenshots and COCO annotations in `ok_templates` for editing
and future exports. Split exports require only the PNG files at runtime.

## Configuration

Add `template_folder` alongside the existing configuration; all variance,
threshold, processor, and center-anchor settings continue to apply:

```python
'template_matching': {
    'coco_feature_json': os.path.join('assets', 'coco_annotations.json'),
    'template_folder': os.path.join('assets', 'templates'),
    'default_horizontal_variance': 0.002,
    'default_vertical_variance': 0.002,
    'default_threshold': 0.8,
    'feature_processor': process_feature,
    # Keep your existing hcenter_features and vcenter_features here.
},
```

`template_folder` defaults to `assets/templates`; set it to `None` to disable the main
split source. `coco_feature_json` can be omitted for applications using only split
templates. Both sources can coexist: split templates override matching COCO names
within the same source group; configured application features retain priority over
custom-script features. Custom scripts automatically load `ok_tasks/assets/templates`
and `ok_tasks/assets/coco_annotations.json`. Imports load both formats under
`ok_import/<module>/assets/` (split crops in `templates/`), using `<module>/<feature>` names.

## Generate templates

To generate split templates programmatically:

```python
from ok.feature.FeatureSet import generate_templates

template_folder = generate_templates(
    coco_json='ok_templates/coco_annotations.json',
    target_folder='assets/templates',
    image_folder='ok_templates',
    generate_label_enmu=None,
)
```

The function returns the output folder. If `image_folder` is omitted, image paths
are resolved relative to the input COCO file. Generation stages and validates the
crops before replacing outputs and removes stale template crops. The destination
must contain only template PNG files. Unparseable filenames produce an error
before export changes any existing files. Source screenshots and annotations are
retained.

## Filenames and validation

A filename has the form `<original_name>_<width>x<height>_<x>_<y>.png`, with no
prefix or name encoding. For example, `douling_heavy_3840x2160_2822_1896.png`
contains feature `douling_heavy` from (2822, 1896) on a 3840 by 2160 screenshot.
The PNG dimensions give the crop width and height. Geometry is parsed from the
right, so spaces, underscores, and Unicode characters in the original name are
preserved. Names that cannot be used in Windows filenames, such as those containing
`/`, `\`, or `:`, are rejected with a clear error instead of being changed.

The loader validates every filename in the selected template folder, even for a
single-feature lookup. Invalid filenames, invalid geometry, and unreadable selected
PNGs raise errors rather than being silently skipped. Regenerate older split
exports from their source annotations to replace encoded filenames.

Export rejects invalid rectangles and conflicting feature names before replacing
existing assets. Names beginning with `box_` represent regions; their crops are
white and should not be used as visual matching templates. Renaming a crop
without preserving its geometry fields changes its meaning; do not edit these
filenames manually.

## Migration and verification

Keep the editable COCO and original screenshots in `ok_templates`. Regenerate
with `generate_templates` into `assets/templates`, then set `template_folder` to
that folder. Keep an existing `coco_feature_json` entry while migrating; split
features take precedence for the same names within that source group.

Regenerating older encoded split exports replaces their filenames with the
original names and removes stale crops. If validation names an unexpected file,
inspect it and move unrelated material outside the export folder before retrying.
Do not strip the old prefix by hand: the old feature name was encoded too.

Verify against a saved source screenshot using the original feature name:

```python
import cv2
from ok.feature.FeatureSet import FeatureSet

features = FeatureSet(False, None, 0.002, 0.002, template_folder=template_folder)
frame = cv2.imread('ok_templates/settings.png')  # Use your actual source screenshot.
boxes = features.find_feature(frame, 'settings_save', threshold=0.95)
assert len(boxes) == 1, boxes
```

Also verify representative screenshots at the supported resolutions. The GUI
Save action reloads its feature set. After programmatic export, refresh cached
features with `feature_set.process_data()` on the executor thread, or restart the
application. Finish export before another task reads these files.

Older Windows exports may have inherited restrictive permissions from a private
temporary directory. Regenerate them with the current library; new files inherit
access permissions from their destination folder. Verify that a normal image
viewer can open them without elevated privileges.
