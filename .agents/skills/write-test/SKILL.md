---
name: write-test
description: Write and run tests for a third-party application's ok-script tasks using its screenshot fixtures, TaskTestCase, and isolated mocks.
---

# Write Automation Tests

Use this skill in the consuming application's project to test its task behavior, recognition, recovery, and settings. Use the installed ok-script test APIs and the application's own config, fixtures, and runner. No library source checkout or separate reference project is required; developing the library's test suite is outside this skill's scope.

## Choose the test boundary

Read the affected implementation, nearby tests, and project test runner before writing a test. Choose the smallest boundary that exercises the real behavior:

| Behavior | Pattern |
| --- | --- |
| Recognition from a saved screen | `TaskTestCase`, the application's real task, `set_image()` |
| Template geometry, resolution, or anchors | Real `FeatureSet` with application assets and image arrays |
| Task decisions and action ordering | Lightweight application task instance with mocked input |
| Retry loops, task chaining, or counters | Real task methods with mocked dependencies and bounded scenarios |
| Persistence and cleanup on failures | Temporary application settings and scoped patches |

Prefer assertions about application behavior over source-text checks, print-only diagnostics, or real-time sleeps. Do not add tests that only mirror implementation details or wording.

## Screenshot tests

Import `TaskTestCase` from `ok.test.TaskTestCase`; set class attributes `task_class` and `config`. Use the project's real config and templates. Copy config values that the harness will mutate so other tests do not inherit those changes; a shallow copy only isolates top-level keys.

The current harness initializes one task per test class, replaces capture with `ImageCaptureMethod`, and uses `DoNothingInteraction`. `set_image(path)` advances the frame and checks template sizing; `set_images(*paths)` installs a sequence and advances its first frame. Read the capture implementation when testing frame progression rather than assuming repeated reads advance it.

- Store reproducible screenshots under the target project's `tests/images/`, or reuse an existing tracked `ok_templates` source when appropriate. Confirm each fixture exists and loads.
- Load the image before calling the recognition method. Exercise real recognition rather than mocking the method being tested.
- Assert the detected state, value, feature name, confidence, or box geometry as appropriate. Include an absent or negative case when it distinguishes the regression.
- For scaling bugs, use representative resolutions and aspect ratios with `subTest`; preserve the intended center/right anchors and allow a justified pixel tolerance. Include positive matches and blank-frame negatives when relevant.
- Reset relevant mutable task state before each scenario. The task is shared across methods; base `tearDown()` only calls `reset_scene()`. Use scoped patches for replaced methods, and call the base lifecycle methods when overriding them.
- Do not treat no-op input as proof that an in-game click worked. Test action intent with mocks; use the [develop skill](../develop/SKILL.md) when actual GUI/MCP interaction is part of the request.
- For fixture annotation or named feature creation, follow [generate-templates](../generate-templates/SKILL.md).

For direct split-template tests, construct `FeatureSet(False, None, 0.002, 0.002,
template_folder=<absolute export folder>)`. For packed COCO tests, pass the JSON
path as the second argument. Match using the original feature name, without the
filename's geometry suffix. Keep test screenshots and reports outside the split
export folder: every filename there is validated, including during lazy lookups.

## Isolated logic tests

Use `unittest.TestCase` and `unittest.mock` for branches that do not require capture, OCR, or the runtime. Construct normally when inexpensive. Where initialization starts the runtime, `TaskClass.__new__(TaskClass)` can isolate a method, provided the test explicitly initializes every field that method uses. A small fake binding a production method is also appropriate for orchestration tests.

- Mock external effects such as input, sleeps, capture, and unrelated task dispatch. Keep the production decision or orchestration method real.
- Use `side_effect` for successive detections or failures. Assert return values and state changes; assert exact action order only when order is part of the behavior, such as checkbox before confirmation.
- Check that absent UI or early exits produce no clicks or other unintended actions with `assert_not_called()`.
- Make retry cases finite and exercise the relevant termination or recovery behavior. Patch the clock in the module where it is used when elapsed time affects the result.
- Use context-managed patches or `addCleanup()` so changes do not leak. Use temporary directories for persistence tests instead of real user config.
- Explain the regression with a brief concrete comment when the expected value is otherwise surprising.

For a confirmation dialog, mock `find_one`, `click`, and `sleep`, supply a checkbox and confirmation button as detections, then invoke the application's real dialog method. Assert that it clicks the checkbox before confirming. A separate absent-dialog case should return without clicks.

## Run and verify

Follow [use-venv](../use_venv/SKILL.md). Run from the application's root using its environment so task imports and relative fixture paths resolve. Install its test dependencies through its normal requirements or lockfile when needed.

Prefer the application's existing test runner. For a pytest application, a focused invocation is:

```powershell
# Working directory: the application's root.
$py = if (Test-Path .\.venv\Scripts\python.exe) { ".\.venv\Scripts\python.exe" } else { "python" }
& $py -m pytest tests/test_settings_task.py -q
```

Replace the example filename with the application's affected test. For an isolated unittest module without a custom runner, use `& $py -m unittest discover -s tests -p 'TestSettingsTask.py' -v`.

Check the application's test naming patterns: default discovery can miss uppercase `Test*.py` filenames. Preserve any process isolation used by its runner. Runtime-backed `TaskTestCase` tests may share a global library runtime; run classes in separate processes when repeated initialization would reuse a destroyed runtime.

Run the changed test and relevant neighboring cases. Verify that tests were actually collected and inspect exit codes; syntax checks alone do not establish a pass. For a regression, confirm that the assertions distinguish the old failure when practical. Report the test command, outcome, and any missing fixture or dependency that prevented execution. If dependencies need repair, follow [setup-env](../setup-env/SKILL.md).
