# Interface and developer tools

[简体中文](../interface.md) · [Documentation](index.md) · [Quick start](quick_start.md) · [API reference](api_reference.md)

ok-script brings task configuration, device connection, scripting, template management, and recognition debugging into one desktop interface. This page explains the tools shown in the current UI screenshots and how they fit together.

## Configure and run tasks

![Task configuration and execution interface](../ok_py/image_tasks.png)

The task page lists the one-time and composite tasks supplied by an application. Expand a task card to:

- change dropdown, numeric, toggle, and multi-select options;
- read help text for each option;
- start an individual task and inspect its state;
- reset the task configuration;
- collapse tasks that do not need editing.

Application developers create these controls with `BaseTask.default_config`, `config_description`, and `config_type`. Users can adjust runtime behavior without editing Python code.

## Select capture and interaction backends

![Capture and interaction interface](../ok_py/image_capture.png)

The capture page connects a target and selects the screen-capture and input backends:

1. Connect a Windows game, emulator, or ADB device under the target list.
2. Select a capture backend. WGC is generally fast, while BitBlt offers broader compatibility.
3. Select an interaction backend, such as `PostMessage` for supported background input.
4. Use the screenshot and OCR developer tools to verify the captured image.
5. Enable recognition boxes while debugging.

If capture works but input does not, check the interaction backend and administrator privileges. See the [quick-start guide](quick_start.md) for setup details.

## Browse scripts and APIs

![Script and API browser](../ok_py/image_scripting.png)

The scripting page keeps task source and reusable API templates together:

- browse APIs by mouse, keyboard, OCR, template matching, ADB, and other categories;
- switch application tasks with the task selector;
- run or record scripts to validate a small automation sequence;
- insert common calls from templates to reduce typing errors.

The built-in editor is useful for inspection and quick experiments. Use PyCharm or VS Code with automated tests for larger changes.

## Manage template assets

![Template asset management interface](../ok_py/image_template.webp)

The template page presents COCO source screenshots and annotation categories as cards. It supports:

- capturing new source screenshots;
- searching by name or category;
- seeing which recognition features belong to each image;
- opening the annotation tool to adjust regions;
- saving optimized template assets.

Annotate at the highest resolution you plan to support. Choose stable, distinctive regions and exclude animated text. See [Template matching with COCO assets](advanced.md#1-template-matching-with-coco-assets) for the complete workflow.

## Inspect the debug overlay

![Debug overlay with template-matching results](../ok_py/image_overlay.webp)

The debug overlay draws recognition state over the captured frame:

- rectangles show search regions and matches;
- labels identify features and may show thresholds or confidence values;
- center guides help verify relative coordinates and screen regions;
- overlapping results reveal templates that are too broad, thresholds that are too low, or inaccurate search regions.

The overlay is a development and diagnostic aid. Production task logic must use values returned by APIs such as `find_one`, `wait_feature`, and `ocr`, not overlay state.

## Recommended workflow

1. Connect the target on the capture page and verify screenshots.
2. Capture and annotate stable features on the template page.
3. Implement the smallest recognition-and-click sequence in the script page or an IDE.
4. Enable the debug overlay and inspect search regions and matches.
5. Package stable behavior into a task and verify its configuration UI.
6. Add regression tests with fixed screenshots before publishing a build.
