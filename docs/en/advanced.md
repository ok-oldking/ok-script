# Advanced guide

[Documentation](index.md) · [Quick start](quick_start.md) · [API reference](api_reference.md) · [简体中文](../after_quick_start/README.md)

This guide covers the workflows normally needed after the template project is running: template assets, localization, repeatable tests, and automated releases.

## 1. Template matching with COCO assets

ok-script stores template annotations in COCO format.

### Why COCO annotations help

- **Position hints:** an annotation records the template's relative position in the source screenshot. The matcher can search a smaller region for better speed and accuracy.
- **Resolution independence:** annotate screenshots at the highest supported resolution, such as 4K. ok-script scales templates down for lower-resolution users.
- **Centralized asset management:** screenshots, categories, and bounding boxes remain connected instead of becoming an unstructured folder of cropped images.

### Workflow

1. Capture representative screenshots at the highest supported resolution.
2. Annotate each reusable UI feature with a COCO-compatible tool. `label-studio==1.15.0` is known to produce compatible exports; newer export formats may differ.
3. Place `result.json` and its image directory under the application's `assets` directory.
4. Run `python main_debug.py` and start the application. Debug mode detects the COCO data, crops annotated regions, and optimizes the templates.
5. Reference category names from methods such as `find_feature`, `find_one`, and `wait_feature`.

Use distinctive regions with minimal animation. Avoid including large backgrounds or changing text in a button template.

## 2. Internationalization

Application translations follow the Qt `.ts`/`.qm` workflow.

### Translation directories

Store gettext application-language files in this structure when the template project uses `.po` files:

```text
i18n/
├── en_US/LC_MESSAGES/ok.po
└── zh_CN/LC_MESSAGES/ok.po
```

After editing translations, use **Compile i18n** in the application's developer tools to generate the binary files loaded at runtime.

For changes to ok-script itself, update every language file under `ok/gui/i18n/`, ensure no translation remains unfinished, and run:

```powershell
.\compile_i18n.cmd
```

## 3. Automated task tests

`TaskTestCase` supplies a controlled task runtime. The key technique is `self.set_image()`, which replaces live capture with a stable screenshot.

```python
from ok.test.TaskTestCase import TaskTestCase
from src.tasks.MyProblematicTask import MyProblematicTask


class TestUserIssue(TaskTestCase):
    task_class = MyProblematicTask

    def test_scenario_from_user_screenshot(self):
        self.set_image("tests/user_screenshots/user_bug_report_01.png")

        result = self.task.some_method_that_failed()

        self.assertIsNotNone(result)
```

This makes recognition tests deterministic and allows a user's uploaded screenshot to become a permanent regression test.

Run all tests from the repository root:

```powershell
python -m pytest tests
```

When running an individual test from PyCharm, set the working directory to the project root so relative paths such as `tests/images/` resolve correctly.

## 4. Packaging and publishing with GitHub Actions

The boilerplate project's `.github/workflows/build.yml` can test, package, and publish releases when a version tag such as `v1.0.0` is pushed. Packaging is driven by [PyAppify](https://github.com/ok-oldking/pyappify) and `pyappify.yml`.

The typical pipeline is:

1. A `v*` tag triggers the workflow.
2. Python and project dependencies are installed.
3. Small Python dependencies may be copied into the update repository.
4. Automated tests run as a release gate.
5. update repositories are synchronized and release notes are generated.
6. PyAppify creates Windows artifacts.
7. GitHub Release publishes the notes and installers.

### Inline small source dependencies

`inline_ok_requirements` includes `ok-script` and `pyappify` by default. Additional small, pure-Python packages can be included with repeated arguments:

```powershell
python -m ok.update.inline_ok_requirements --tag "$env:RELEASE_TAG" `
  --add-inlined-requirement custom-package=custom_package `
  --add-inlined-requirement another-package=another_package
```

`PACKAGE` is the distribution name in `requirements.txt`; `FOLDER` is the package directory in `site-packages`. Large assets and platform-specific binaries should stay in the normal dependency and packaging flow.

### Regional update sources

Multiple `profiles` in `pyappify.yml` can produce builds with different update repositories:

```yaml
name: "my-app"
uac: true

profiles:
  - name: "China"
    git_url: "https://example.cn/owner/update.git"
  - name: "Global"
    git_url: "https://github.com/owner/update.git"
```

Each profile embeds its own update URL. A mainland China mirror can therefore coexist with a global GitHub source.

### Build artifacts

A release commonly contains:

- a complete installer for each profile;
- an online installer that downloads resources;
- a launcher archive used to accelerate the next build.

The launcher archive is a build cache and is not normally intended for end users.

### Reuse a previous launcher

If only task code changed, a workflow can reference a launcher from an earlier release and avoid rebuilding it:

```yaml
use_release: https://api.github.com/repos/OWNER/REPOSITORY/releases/tags/v1.0.0
```

Update the URL to a release containing the compatible launcher archive.
