---
name: generate-templates
description: Create template matching assets for a third-party ok-script application from its screenshots and COCO annotations, then verify them with find_feature or find_one.
---

# Generate and use templates

Work on the consuming application's screenshots, annotations, task code, and
assets using the installed library. All project-relative paths below refer to
that application's root, not the ok-script library directory.

Use the existing pipeline: original screenshots in `ok_templates/`, annotations
in `ok_templates/coco_annotations.json`, and `compress_copy_coco` to generate
runtime assets. Keep source screenshots intact so both agents and the Template
tab can inspect and reannotate them. No new asset format or MCP tools are needed.

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

Use the same function as the Template tab's Save action:

```python
from ok.feature.FeatureSet import compress_copy_coco

generated_json = compress_copy_coco(
    coco_json=str(store.coco_path),
    target_folder=str(Path("assets").resolve()),
    image_folder=str(store.folder),
    generate_label_enmu=None,
)
print(generated_json)
```

Choose the destination from the existing project config: normally `assets` for
a standalone app, or `ok_tasks/assets` for custom scripts. The main config uses
`template_matching.coco_feature_json`; preserve its other matching settings.
Custom task assets are merged automatically when the configured feature set
loads. Check for conflicting feature names in the main and custom datasets.

Before calling the exporter, resolve source and destination paths and ensure
they are separate, non-overlapping directories. The exporter deletes the target
`images/` tree and EVERY top-level `.json` file, so verify these contain only
generated template data and retain a recoverable copy of an existing export.
If unrelated assets share this destination, use a dedicated template subfolder
and update the relevant main config path; do not delete unrelated files. The
automatic custom-script merge specifically expects `ok_tasks/assets/coco_annotations.json`.

Validate all referenced source files, their recorded dimensions, category/image
IDs, and bounding boxes before generation. Missing sources can be skipped by
the exporter rather than producing a useful failure. Never call `compress_coco`
on the source `ok_templates` dataset; it is an in-place transformation. Keep
the prior generated COCO available when regenerating: the exporter uses it to
preserve packed image page assignments.

The optional keyword is spelled `generate_label_enmu` in the existing API. Its
value is a dotted module/class path, e.g. `ok_tasks.LabelEnum`, not a filename.
Use it only when the project uses enums; every category must be a valid Python
identifier and not a keyword. Verify the generated enum imports successfully.

## Verify and use the feature

First load generated assets in a fresh `FeatureSet` and match the original
screenshot. This checks the full annotation/export/load path without a GUI:

```python
from ok.feature.FeatureSet import FeatureSet

features = FeatureSet(False, generated_json, 0.002, 0.002,
                      default_threshold=0.95)
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
