import os
import subprocess
import sys
import unittest


class TestHeadlessImports(unittest.TestCase):
    def test_core_imports_without_qt_packages(self):
        source = (
            "import sys; "
            "sys.modules['PySide6'] = None; "
            "sys.modules['qfluentwidgets'] = None; "
            "sys.modules['packaging'] = None; "
            "sys.modules['mcp'] = None; "
            "import ok; "
            "from ok import Icon; "
            "from ok.core.events import communicate; "
            "from ok.core.plugins import github_release_assets; "
            "from ok.task.task import BaseTask; "
            "from ok.task.TaskExecutor import TaskExecutor; "
            "from ok.util.GlobalConfig import basic_options"
        )
        result = subprocess.run(
            [sys.executable, "-c", source],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_semantic_icons_do_not_load_qt(self):
        source = (
            "import sys; "
            "sys.modules['PySide6'] = None; "
            "sys.modules['qfluentwidgets'] = None; "
            "from ok import ConfigOption, Icon; "
            "option = ConfigOption('Character Config', icon=Icon.PEOPLE); "
            "assert option.icon == 'people'"
        )
        result = subprocess.run(
            [sys.executable, "-c", source],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_qt_ui_imports_without_fluent_widgets(self):
        # Every UI module must load with only PySide6 present.
        source = (
            "import sys, pkgutil, importlib; "
            "sys.modules['qfluentwidgets'] = None; "
            "sys.modules['qframelesswindow'] = None; "
            "import ok.ui.qt as qt; "
            "names = [m.name for m in pkgutil.walk_packages(qt.__path__, 'ok.ui.qt.')]; "
            "[importlib.import_module(name) for name in names]; "
            "print(len(names))"
        )
        result = subprocess.run(
            [sys.executable, "-c", source],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        )
        self.assertEqual(0, result.returncode, result.stderr[-3000:])
        self.assertGreater(int(result.stdout.strip().splitlines()[-1]), 40)


if __name__ == "__main__":
    unittest.main()
