---
name: write-test
description: Write and run ok-script automation regression tests using screenshot fixtures, TaskTestCase, and isolated unittest mocks, following the ok-wuthering-waves test patterns.
---

# Write Automation Tests

Use this skill for regression tests in ok-script and automation projects built on it. The reference suite is `E:/projects/ok-wuthering-waves/tests`; adapt its patterns to the target project's classes, config, fixtures, and runner. Do not make new tests depend on that checkout. Keep the target repository's existing test naming and framework conventions.

## Choose the test boundary

Read the affected implementation, nearby tests, and project test runner before writing a test. Choose the smallest boundary that exercises the real behavior:

| Behavior | Pattern | Reference example |
| --- | --- | --- |
| Recognition from a saved screen | `TaskTestCase`, real task, `set_image()` | `TestCombatCheck.py` |
| Template geometry, resolution, or anchors | `unittest.TestCase`, real `FeatureSet`, image arrays | `TestFeatureSet.py` |
| Task decisions and action ordering | `unittest.TestCase`, lightweight task instance, mocks | `TestSkipDialogConfirm.py` |
| Retry loops, task chaining, or counters | Small fake binding real production methods | `TestFarmEchoTaskEchoRate.py` |
| Character action branches | Real character with a mocked task and action methods | `test_suoming.py` |
| Persistence and cleanup on failures | Temporary directories and scoped patches | `TestMultiAccountConfig.py` |

These examples are optional reading when the reference checkout is available. Prefer behavior assertions over copying the suite's AST checks, print-only diagnostics, or real-time sleeps. Do not add tests that only mirror implementation details or wording.

## Screenshot tests

Import `TaskTestCase` from `ok.test.TaskTestCase`; set class attributes `task_class` and `config`. Use the project's real config and templates. Copy config values that the harness will mutate so other tests do not inherit those changes; a shallow copy only isolates top-level keys.

The current harness initializes one task per test class, replaces capture with `ImageCaptureMethod`, and uses `DoNothingInteraction`. `set_image(path)` advances the frame and checks template sizing; `set_images(*paths)` installs a sequence and advances its first frame. Read the capture implementation when testing frame progression rather than assuming repeated reads advance it.

- Store reproducible screenshots under the target project's `tests/images/`, or reuse an existing tracked `ok_templates` source when appropriate. Confirm each fixture exists and loads.
- Load the image before calling the recognition method. Exercise real recognition rather than mocking the method being tested.
- Assert the detected state, value, feature name, confidence, or box geometry as appropriate. Include an absent or negative case when it distinguishes the regression.
- For scaling bugs, use representative resolutions and aspect ratios with `subTest`; preserve the intended center/right anchors and allow a justified pixel tolerance. `TestFeatureSet.py` demonstrates positive matches and blank-frame negatives.
- Reset relevant mutable task state before each scenario. The task is shared across methods; base `tearDown()` only calls `reset_scene()`. Use scoped patches for replaced methods, and call the base lifecycle methods when overriding them.
- Do not treat no-op input as proof that an in-game click worked. Test action intent with mocks; use the [develop skill](../develop/SKILL.md) when actual GUI/MCP interaction is part of the request.
- For fixture annotation or named feature creation, follow [generate-templates](../generate-templates/SKILL.md).

## Isolated logic tests

Use `unittest.TestCase` and `unittest.mock` for branches that do not require capture, OCR, or the runtime. Construct normally when inexpensive. Where initialization starts the runtime, `TaskClass.__new__(TaskClass)` can isolate a method, provided the test explicitly initializes every field that method uses. A small fake binding a production method is also appropriate for orchestration tests.

- Mock external effects such as input, sleeps, capture, and unrelated task dispatch. Keep the production decision or orchestration method real.
- Use `side_effect` for successive detections or failures. Assert return values and state changes; assert exact action order only when order is part of the behavior, such as checkbox before confirmation.
- Check that absent UI or early exits produce no clicks or other unintended actions with `assert_not_called()`.
- Make retry cases finite and exercise the relevant termination or recovery behavior. Patch the clock in the module where it is used when elapsed time affects the result.
- Use context-managed patches or `addCleanup()` so changes do not leak. Use temporary directories for persistence tests instead of real user config.
- Explain the regression with a brief concrete comment when the expected value is otherwise surprising.

For example, the reference dialog tests create `BaseWWTask` with `__new__`, mock `find_one`, `click`, and `sleep`, feed `[confirm, checkbox]` through `find_one.side_effect`, invoke the real `click_skip_dialog_confirm()`, and assert a true result and clicks in `[checkbox, confirm]` order. A separate absent-dialog case asserts false and no clicks.

## Run and verify

Follow [use-venv](../use_venv/SKILL.md). Run from the target project root so imports and relative fixture paths resolve. Use that project's environment for its tests and the framework environment for framework checks.

For ok-wuthering-waves, the existing `run_test.py` runs one unittest module per process. It disables background OCR warmup while retaining synchronous real OCR when needed, and sets a portable oneDNN CPU path before loading native libraries. Prefer this runner rather than bypassing it:

```powershell
# Working directory: the target project root.
$py = if (Test-Path .\.venv\Scripts\python.exe) { ".\.venv\Scripts\python.exe" } else { "python" }
& $py -u .\run_test.py .\tests\TestSkipDialogConfirm.py
```

Use the target project's own runner when it differs. For an isolated unittest module without a custom runner, use `& $py -m unittest discover -s tests -p 'TestSkipDialogConfirm.py' -v`. In ok-script, follow its existing pytest style and run a focused file with `& $py -m pytest tests/test_skills.py -q` (replace the filename with the affected test).

The reference suite mixes `Test*.py` and `test_*.py`; default discovery may miss uppercase filenames. Its CI enumerates `tests/*.py` and launches each separately. Preserve process isolation for runtime-backed tests: the current `ok.test` harness holds a global runtime, and `destroy_ok()` quits it without clearing that reference. Do not assume multiple runtime test classes can safely restart it in one process.

Run the changed test and relevant neighboring cases. Verify that tests were actually collected and inspect exit codes; syntax checks alone do not establish a pass. For a regression, confirm that the assertions distinguish the old failure when practical. Report the test command, outcome, and any missing fixture or dependency that prevented execution. If dependencies need repair, follow [setup-env](../setup-env/SKILL.md).
