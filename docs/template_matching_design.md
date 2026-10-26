# Screenshot-first template matching

Status: superseded proposal. The selected approach uses existing functions:
preserve original screenshots under `ok_templates`, update its COCO annotations,
call `compress_copy_coco` to generate assets, and use `find_feature`/`find_one`.
The [generate-templates skill](../.agents/skills/generate-templates/SKILL.md)
documents this workflow. The alternative APIs and commands below are not
implemented and are not required for the selected approach.

## Goal

A coding agent should be able to capture an application, create a named template
from a rectangle, inspect matching against that exact screenshot, and reproduce
the result offline. It should not need to drive an annotation GUI, hand-edit COCO
IDs, or lower thresholds blindly. Human authors should use the same storage and
matching services through the Template tab.

## Current implementation

- `ok/core/template_store.py` already provides headless COCO storage, screenshot
  saving, and annotation replacement. Extend this rather than create a second
  unrelated asset editor.
- `ok/feature/FeatureSet.py` combines loading, resizing, search-region selection,
  preprocessing, matching, filtering, and Qt diagnostic emissions.
- `ok/task/task.py` already accepts `frame=` and `template=` in `find_feature`.
  Preserve this useful route for reproducible matching.
- Named templates carry their source position into matching. Search scope and
  crop geometry are consequently coupled through variance parameters.
- Zero means “use the default” for threshold and variances, so an explicit zero
  cannot always express the caller's intent.
- Failed matching usually yields an empty list. `screenshot=True` emits images
  through Qt but does not provide a structured, synchronously saved explanation.
- The loader stores one feature per category. Duplicate annotations can be
  skipped or rejected; they are not an explicit appearance-variant system.
- MCP screenshots already supply paths, dimensions, capture time, and freshness.
  Keep using these observations and the existing task submission contract.

## Recommended workflow

1. Capture once through MCP, or use a user-provided image. Record the original
   pixels, dimensions, hash, and available capture metadata.
2. Inspect that image. If a resized preview or a detail crop is needed, generate
   it with an explicit transform back to original image coordinates.
3. Create a template with a semantic name and a rectangle in original pixels.
   Immediately produce a crop preview and a full-image annotation preview.
4. Inspect matching on the same saved image, then on independent positive and
   negative screenshots. Inspect scores, candidates, and the actual search area.
5. Use the named feature in task code. Verify real application behavior and
   success conditions using the existing reset/run workflow.
6. Keep useful independent screenshots as regression fixtures. A match against
   the source crop alone is a smoke check, not evidence of robustness.

## Asset authoring

Add a headless `TemplateRepository` facade backed by `CocoTemplateStore`. Give it
operations for `list`, `describe`, `add_from_screenshot`, `update`, `preview`,
and explicit `export`. Adding one annotation must preserve neighboring ones;
the agent should not need to call whole-image `replace_annotations` itself.

Example proposed Python interface:

```python
repo = TemplateRepository("ok_templates")
asset = repo.add_from_screenshot(
    name="settings.save",
    image_path="tests/screens/settings-open.png",
    crop=PixelRect(x=1480, y=920, width=160, height=48),
    search=NormalizedRect(x=0.65, y=0.70, width=0.35, height=0.30),
    scale=ScalePolicy.fixed(),
    threshold=0.95,
)
asset.write_preview("artifacts/settings-save")
```

The crop selects the pixels to recognize. The search region says where to look
on another frame. Neither implies the other. New assets default to full-frame
search and fixed pixel scale; previews should encourage an explicit search
region when the layout supports it. Existing COCO assets retain their current
position and scaling behavior through a legacy adapter.

Keep COCO images and annotations as the geometry source of truth. Add a versioned
`features.json` sidecar for recognition policies and provenance, keyed by stable
feature/variant IDs and referencing COCO annotation IDs. Include source hash,
reference dimensions, threshold, search policy, scale policy, preprocessing,
optional mask path, and a short description. Preserve existing image formats;
new captures and derived crops use lossless PNG.

Do not duplicate crop geometry in both files. The sidecar and annotations form
one repository revision: validate all references, stage changes, and publish an
atomic revision pointer only after all files are ready. Readers retain their
previous snapshot on incomplete revisions. Serialize writers across processes
and reject edits based on an obsolete revision. A thread lock alone is
insufficient for simultaneous GUI and agent edits.

Reject unreadable images, non-finite coordinates, empty/out-of-bounds crops,
duplicate names without an explicit update, and inconsistent masks. Do not
silently clamp a mistaken agent rectangle or replace corrupt metadata with an
empty dataset. A separate explicit clipping operation can support interactive
GUI dragging. Restrict manifest references to repository files.

Preserve source screenshots during authoring. Export cropped/packed deployment
assets explicitly using the existing compression infrastructure. Matching and
inspection must never rewrite source assets. Runtime configuration selects the
authoring repository or exported snapshot explicitly; do not silently prefer
`ok_templates` over configured application assets or imported namespaces.

## One matching engine, two interfaces

Extract a pure engine that takes a frame, resolved template, and options. It must
not require a running GUI, capture backend, or executor. Runtime matching,
offline inspection, and GUI previews all call this engine.

Keep the existing convenience API and return types:

```python
boxes = self.find_feature("settings.save")  # list[Box]
box = self.find_one("settings.save")        # Box or None
```

Add a separate explicit inspection API rather than make `find_feature` return
different types depending on a debug flag:

```python
report = matcher.inspect(
    frame=FrameSnapshot.from_file("tests/screens/settings-open.png"),
    feature="settings.save",
    options=MatchOptions(threshold=0.95, candidate_limit=5),
)
report.write("artifacts/save-match")
```

New options use `None` for inheritance. Define precedence as explicit call
options, feature policy, repository defaults. Legacy wrappers retain the zero
sentinels and existing ordering/limit semantics. Compatibility fixtures should
cover these behaviors before routing wrappers through the extracted engine.

Use explicit `PixelRect` and `NormalizedRect` types, with `(x, y, width, height)`
and half-open bounds. Returned boxes always refer to original capture pixels.
Track ROI offsets and resize transforms and apply each exactly once. Display,
desktop, and input coordinates are separate: the existing interaction backend
remains responsible for converting capture coordinates to input coordinates.

Support fixed pixel scale and the existing resolution transform first. Add
bounded explicit scale ranges later; do not infer UI scale from screenshot
dimensions alone. DPI, letterboxing, and responsive layout can break that
assumption. Reports record the actual scale and search rectangle used.

## Match reports

Every inspection produces a bounded `report.json` and an `overlay.png`, plus
the actual processed template and search image. Save these synchronously before
returning paths. Optionally include a heatmap and candidate contact sheet.
All output paths are absolute; numeric fields contain no NaN or infinity.

The report includes:

| Field | Purpose |
| --- | --- |
| Schema/engine version, asset revision and hashes | Reproduce the exact inputs |
| Frame size, capture timestamp, cached flag if known | Establish image identity and freshness |
| Effective options, ROI, template size, scale and transforms | Explain what was actually searched |
| Accepted boxes with feature/variant IDs and scores | Supply normal matching results |
| Best rejected candidates and thresholds | Explain near misses without accepting them |
| Distinct runner-up score and score gap | Surface competing locations |
| Status and warnings | Distinguish a miss from invalid input or numerical failure |
| Timings and artifact paths | Diagnose cost and inspect evidence |

Candidate extraction must suppress overlapping peaks before identifying a
runner-up; adjacent pixels around the same peak are not independent matches.
Keep rejected candidates clearly separate from accepted boxes. Inspection must
not silently widen the ROI or lower thresholds. An optional exploratory search
outside the ROI is a separate labeled result, never a runtime success.

Use statuses such as `matched`, `no_match`, `invalid_input`, and
`numerical_failure`, plus warnings such as `ambiguous`, `low_texture`, and
`template_larger_than_roi`. Invalid geometry must be caught before OpenCV runs.
Constant templates and non-finite response maps must not become confident hits.
Do not present correlation scores as probabilities.

Initially support the existing default normalized correlation in the new API.
For additional methods, define score direction and threshold meaning explicitly;
lower-is-better methods must not go through higher-is-better filtering. Preserve
legacy entry points separately until each method has compatibility coverage.

Reports are opt-in to avoid disk I/O on every polling iteration. A task can save
one report on a final timeout using the exact frame that failed. The report
should carry capture identity; a saved box is not authorization to click that
location on a changed live screen. Reobserve before acting when state changes.

## Local CLI and GUI

Expose the same services through proposed local commands:

```text
python -m ok templates add --repo ok_templates --image tests/screens/settings-open.png --name settings.save --crop 1480 920 160 48
python -m ok templates inspect --repo ok_templates --feature settings.save --image tests/screens/settings-open.png --out artifacts/save-match
python -m ok templates validate --repo ok_templates --cases tests/vision/cases.json --out artifacts/vision
```

Commands emit a compact JSON summary and absolute artifact paths. Distinguish
execution/configuration errors from a valid inspection that found no match.
Validation exits unsuccessfully if any expected result fails. Use the project
venv when invoking these commands, following the repository interpreter skill.

The Template tab uses these services for annotation, crop preview, and a “Test
against screenshot” action. An agent uses local Python/CLI and views the saved
images directly. No additional MCP editing or log-reading tools are needed.
Document this loop in the develop skill once the APIs actually exist.

## Variants and caching

After the basic workflow works, permit explicit named variants under a logical
feature, such as light/dark or enabled/disabled. Do not automatically reinterpret
every duplicate COCO annotation as a variant. Match each eligible variant and
deduplicate overlapping results across variants; report which one won. Distinct
interaction states should normally remain separate logical features.

Cache decoded assets and preprocessing by content hash, variant, mask hash,
preprocessing parameters, and effective scale. Snapshot the repository revision
at the start of a match so an edit cannot mix old pixels with new metadata.
Invalidate changed entries after an atomic edit without restarting the runtime.
For arbitrary preprocessing callbacks, disable derived caching unless the caller
provides a stable cache key. Avoid the current implicit reuse of a single mask
when the requested mask function changes.

## Delivery and acceptance

1. **Inspectable matching:** extract the engine, preserve legacy results, add
   offline inspection and synchronous artifacts. Verify original-coordinate
   boxes after ROI cropping and downsampling, empty frames, oversized templates,
   repeated controls, constant inputs, and invalid/non-finite results.
2. **Screenshot authoring:** add repository operations, preview generation,
   sidecar policies, CLI, and revision-aware reload. Verify crop pixels against
   their source, neighboring annotations survive edits, corrupt repositories
   fail visibly, and concurrent writers cannot lose updates.
3. **Regression validation:** define cases with image paths, expected counts,
   labeled rectangles and localization tolerances, including expected absence.
   Report false positives, false negatives, and localization failures. Include
   independent positive/negative images and representative target sizes; keep
   threshold-tuning images separate from held-out validation cases.
4. **GUI integration and variants:** connect the Template tab to the same
   services, then add explicit variants and bounded scale exploration based on
   actual failures. Verify identical effective inputs produce identical matches
   through the runtime, CLI, and GUI.

The first useful release is steps 1 and 2: capture a screenshot, author a crop,
inspect a match, and use the named asset without manually editing COCO or
restarting the application. More advanced recognition should follow evidence
from that workflow.
