---
name: generate-templates
description: Create template matching assets for a third-party ok-script application from its screenshots and COCO annotations, then verify them with find_feature or find_one.
---

# Generate and use templates

Work on the consuming application's screenshots, annotations, task code, and
assets using the installed library. All project-relative paths below refer to
that application's root, not the ok-script library directory.

Use the existing pipeline: original screenshots in `ok_templates/`, annotations
in `ok_templates/coco_annotations.json`, and `generate_templates` to generate
split runtime assets. Keep source screenshots intact so both agents and the
Template tab can inspect and reannotate them. The old compression APIs and dialog
option are obsolete; use the split exporter for new or regenerated assets.

Run from the automation project's root using its interpreter, following
[use-venv](../use_venv/SKILL.md). For live capture and task execution follow
[develop](../develop/SKILL.md), including reset, baseline verification, and
application-level success checks.

## Capture and choose the rectangle

Use an existing original screenshot or the MCP `screenshot()` result. Check its
dimensions, `captured_at`, and `cached` before treating it as current evidence.
Copy the original file into `ok_templates/` under an unused filename; reuse it
if already there. Do not overwrite a different image with the same name. Keep
files directly in this folder: the exporter resolves source images by basename.
For an in-memory frame, `CocoTemplateStore.save_frame(frame)` saves a PNG and
registers it in COCO; do not register the same frame repeatedly during iteration.

View the actual screenshot before choosing a rectangle. COCO `bbox` is
`[x, y, width, height]` in original screenshot pixels, not two corners or desktop
coordinates. Map any resized preview coordinates back to the original. Choose
a distinctive, stable patch; avoid animation, changing text, and flat colors.
Save and inspect a crop preview before generating assets. Preserve full source
dimensions and location because the matcher uses them for scaling and search.

## Update source annotations

Use `ok.core.template_store.CocoTemplateStore`. Validate existing JSON with
`json.load` before mutation: `store.load()` otherwise treats malformed JSON as
empty. Serialize GUI and agent edits; the store's lock is only process-local.

`replace_annotations(image_name, annotations)` replaces ALL annotations on that
image. Read them first and preserve unrelated entries. Validate positive integer
dimensions and bounds yourself because the store silently clamps rectangles.
Use unique category names across the dataset; duplicate categories on different
images are not supported appearance variants. Prefer Python identifiers such
as `settings_save` if generating a label enum. Names beginning with `box_` are
region annotations whose pixels are omitted during export; do not use that
prefix for a visual template.

Example after copying `settings-open.png` into `ok_templates` (adapt coordinates
to the image you inspected):

```python
import json
from pathlib import Path
import cv2
from ok.core.template_store import CocoTemplateStore

store = CocoTemplateStore("ok_templates")
if store.coco_path.exists():
    with store.coco_path.open(encoding="utf-8") as stream:
        json.load(stream)  # Stop on corrupt metadata before calling store.load().
image_name, name = "settings-open.png", "settings_save"
x, y, width, height = 1480, 920, 160, 48
source = cv2.imread(str(store.image_path(image_name)))
assert source is not None
assert 0 <= x < x + width <= source.shape[1]
assert 0 <= y < y + height <= source.shape[0]
data = store.load()
category_ids = {c["id"] for c in data["categories"] if c["name"] == name}
image_ids = {i["id"] for i in data["images"] if i["file_name"] == image_name}
assert not any(a["category_id"] in category_ids and a["image_id"] not in image_ids
               for a in data["annotations"]), "Feature name belongs to another image"
annotations = store.annotations_for(image_name)["annotations"]
annotations = [a for a in annotations if a["category"] != name]
annotations.append({"category": name, "bbox": [x, y, width, height]})
store.replace_annotations(image_name, annotations)
preview = Path("logs/template-preview")
preview.mkdir(parents=True, exist_ok=True)
assert cv2.imwrite(str(preview / f"{name}.png"), source[y:y+height, x:x+width])
```

If intentionally moving an existing feature to another source image, remove its
old annotation while preserving the others, then add the replacement. If editing
COCO directly, preserve unique IDs, image/category references, dimensions, and
all unrelated entries. Review the annotation diff before export.

## Generate runtime assets

### Split exports (default)

The Template tab defaults to **Split(Recommend)**. Use its split exporter:

```python
from ok.feature.FeatureSet import generate_templates

template_folder = generate_templates(
    coco_json=str(store.coco_path),
    target_folder=str(Path("assets/templates").resolve()),
    image_folder=str(store.folder),
    generate_label_enmu=None,
)
print(template_folder)
```

The Save dialog keeps `assets` and `ok_tasks/assets` as its destination choices;
Split adds the `templates` subfolder. Use `assets/templates` for a standalone app
(`template_matching.template_folder`, which defaults to `assets/templates`), or
`ok_tasks/assets/templates` for custom scripts. Split exports
contain one crop-sized PNG per feature, named
`<original_name>_<width>x<height>_<x>_<y>.png`. Names are readable, with no prefix
or encoding. Spaces, underscores, and Unicode names are supported; characters
forbidden in Windows filenames produce an error. They need no COCO JSON at runtime.
Keep the destination dedicated to template PNGs: both export and loading report
unparseable filenames instead of ignoring them. The exporter preserves the
authoring dataset and replaces/removes template crops. Keep source and destination
separate.

Use the original name in task code: `self.find_one("settings_save")` loads
`settings_save_1920x1080_1480_920.png`. The PNG dimensions supply the crop size;
the filename supplies the reference resolution and top-left position. Do not
rename a crop to work around an annotation error: correct the source annotation
and regenerate. Keep previews, notes, and unrelated files outside this folder;
even a single-feature lookup validates all filenames in the selected folder.

`template_matching.template_folder` and the existing `coco_feature_json` can
coexist; split templates override matching COCO names in
the same source group. Keep existing thresholds, processors, and anchor settings.
Main application features retain priority over custom-script features. Imported
split assets use `ok_import/<module>/assets/templates` and are addressed as
`<module>/<original_name>`.
See [the format documentation](../../../docs/feature-crops.md) for details.

When migrating older encoded split exports, regenerate from the source COCO and
screenshots into the same dedicated folder. The exporter replaces the old files
with readable names. If an export folder contains an unparseable file, inspect
and relocate that file before retrying; export leaves existing files intact on
validation failure. Re-export with the current library to repair older Windows
exports that viewers cannot open because of temporary-directory permissions.

`generate_templates` uses the optional keyword `generate_label_enmu`. Its
value is a dotted module/class path, e.g. `ok_tasks.LabelEnum`, not a filename.
Use it only when the project uses enums; every category must be a valid Python
identifier and not a keyword. Verify the generated enum imports successfully.

## Verify and use the feature

First load generated assets in a fresh `FeatureSet` and match the original
screenshot. This checks the full annotation/export/load path without a GUI:

```python
from ok.feature.FeatureSet import FeatureSet

features = FeatureSet(False, None, 0.002, 0.002,
                      default_threshold=0.95, template_folder=template_folder)
boxes = features.find_feature(source, name, threshold=0.95)
assert len(boxes) == 1, boxes
box = boxes[0]
assert abs(box.x - x) <= 1 and abs(box.y - y) <= 1
assert box.width == width and box.height == height
print(box)
```

Also test an independent positive screenshot and a negative screenshot when
available, and relevant target sizes. A source-image self-match alone does not
prove recognition is robust. Use the project's actual threshold, preprocessing,
and anchor settings for representative verification. Keep evidence of what was
tested and what remains unverified.

In task code, use the existing methods:

```python
box = self.find_one("settings_save", threshold=0.95)
assert box is not None, "Save button not found"
self.click_box(box)
# Observe and assert the resulting application state.
```

`find_feature` returns a list; `find_one` returns a box or `None`. Pass `frame=`
to match a particular screenshot in task code. Named features search near their
annotated position by default. For a control that moves, provide an appropriate
`box=` or explicit horizontal/vertical variances. Variances are fractions of the
frame size, and zero inherits configured defaults. Diagnose capture size,
scaling, crop, and search area before lowering a threshold. `screenshot=True`
uses the existing screenshot worker and may write asynchronously; offline crop
previews should use synchronous `cv2.imwrite` as above.

After regeneration, cached features in a running process must be refreshed.
The GUI Save action already calls `feature_set.process_data()`. For agent edits,
after export finishes call `self.executor.feature_set.process_data()` from the
executor-owned task before matching (after capture initializes frame dimensions),
or restart the verified owned runtime. Do not regenerate files while a task is
reading them or reload from a competing thread.

Finish by reporting the original screenshot, source COCO, generated asset path,
feature names, task usage, and verification evidence. Keep originals and source
annotations for future edits; runtime code uses the generated assets.
