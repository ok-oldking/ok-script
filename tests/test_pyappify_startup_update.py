import importlib
import importlib.util
import json
import os
import sys
import unittest
from types import SimpleNamespace
from contextlib import contextmanager
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

HELPER_PATH = PROJECT_ROOT / "ok" / "gui" / "util" / "pyappify_startup.py"
PYAPPIFY_ENV_KEYS = [
    "PYAPPIFY_APP_VERSION",
    "PYAPPIFY_APP_STARTING_VERSION",
    "PYAPPIFY_UPDATE_NOTE",
]


def load_helper():
    spec = importlib.util.spec_from_file_location("pyappify_startup_under_test", HELPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def simulated_pyappify_env(app_version, starting_version, notes=None):
    previous = {key: os.environ.get(key) for key in PYAPPIFY_ENV_KEYS}
    os.environ["PYAPPIFY_APP_VERSION"] = app_version
    os.environ["PYAPPIFY_APP_STARTING_VERSION"] = starting_version
    os.environ["PYAPPIFY_UPDATE_NOTE"] = json.dumps(notes or [])
    try:
        import pyappify
        yield importlib.reload(pyappify)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        import pyappify
        importlib.reload(pyappify)


class TestPyappifyStartupUpdate(unittest.TestCase):
    def test_update_env_builds_update_success_dialog_text(self):
        with simulated_pyappify_env("1.0.3", "1.0.2", ["Added update notice", "Fixed startup notes"]) as pyappify:
            version_change = load_helper().get_startup_version_change(pyappify)

        self.assertEqual("update success 1.0.2 -> 1.0.3", version_change.title)
        self.assertEqual("Added update notice\nFixed startup notes", version_change.content)

    def test_downgrade_env_builds_downgrade_success_dialog_text(self):
        with simulated_pyappify_env("1.0.2", "1.0.3", ["Rolled back unstable release"]) as pyappify:
            version_change = load_helper().get_startup_version_change(pyappify)

        self.assertEqual("downgrade success 1.0.3 -> 1.0.2", version_change.title)
        self.assertEqual("Rolled back unstable release", version_change.content)

    def test_same_version_env_does_not_show_dialog(self):
        with simulated_pyappify_env("1.0.3", "1.0.3", ["No visible change"]) as pyappify:
            version_change = load_helper().get_startup_version_change(pyappify)

        self.assertIsNone(version_change)

    def test_missing_pyappify_update_api_is_treated_as_not_updated(self):
        old_pyappify = SimpleNamespace(
            app_version="1.0.3",
            app_starting_version="1.0.2",
            get_update_notes=lambda: ["Would have been an update"],
        )

        version_change = load_helper().get_startup_version_change(old_pyappify)

        self.assertIsNone(version_change)

    def test_chinese_and_extra_long_update_notes_are_preserved(self):
        long_note = "很长的更新说明：" + "修复启动提示、关于页面跳转和更新日志展示。" * 120
        notes = [
            "新增：升级后自动打开关于页面。",
            "修复：降级后也会显示对应的更新说明。",
            long_note,
        ]

        with simulated_pyappify_env("1.0.4", "1.0.3", notes) as pyappify:
            version_change = load_helper().get_startup_version_change(pyappify)

        self.assertEqual("update success 1.0.3 -> 1.0.4", version_change.title)
        self.assertEqual("\n".join(notes), version_change.content)
        self.assertIn("新增：升级后自动打开关于页面。", version_change.content)
        self.assertIn(long_note, version_change.content)

    def test_beta_version_vs_release_version_follows_pyappify_api(self):
        with simulated_pyappify_env("1.0.3", "1.0.3-beta", ["Release build is available"]) as pyappify:
            self.assertFalse(pyappify.is_app_updated())
            self.assertFalse(pyappify.is_app_downgraded())
            version_change = load_helper().get_startup_version_change(pyappify)

        self.assertIsNone(version_change)

    def test_about_tab_shows_update_note_above_other_projects(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        long_note = "很长的更新说明：" + "修复启动提示、关于页面跳转和更新日志展示。" * 40
        notes = ["新增：升级后自动打开关于页面。", long_note]

        with simulated_pyappify_env("1.0.4", "1.0.3", notes):
            from PySide6.QtWidgets import QApplication
            from ok.gui.about.AboutTab import AboutTab

            app = QApplication.instance() or QApplication([])
            tab = AboutTab({
                "gui_icon": ":/icon/icon.ico",
                "gui_title": "demo",
                "version": "1.0.4",
                "debug": False,
            })

        widgets = [
            item.widget()
            for i in range(tab.vBoxLayout.count())
            if (item := tab.vBoxLayout.itemAt(i)) and item.widget()
        ]
        titled_widgets = [
            widget
            for widget in widgets
            if hasattr(widget, "titleLabel")
        ]
        titles = [widget.titleLabel.text() for widget in titled_widgets]
        update_index = titles.index("update success 1.0.3 -> 1.0.4")
        projects_index = titles.index("Other Projects")

        self.assertLess(update_index, projects_index)
        self.assertEqual("\n".join(notes), titled_widgets[update_index].widget.text())
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
