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
            "import ok; "
            "from ok.core.events import communicate; "
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


if __name__ == "__main__":
    unittest.main()
