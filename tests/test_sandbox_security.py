import logging
import os
import sys
import types
import unittest

# Stub ok package
_ok_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "ok"))
_stub_ok = types.ModuleType("ok")
_stub_ok.__path__ = [_ok_dir]
_stub_ok.__package__ = "ok"
sys.modules["ok"] = _stub_ok
_ok_util = types.ModuleType("ok.util")
_ok_util.__path__ = [os.path.join(_ok_dir, "util")]
_ok_util.__package__ = "ok.util"
sys.modules["ok.util"] = _ok_util
_ml = types.ModuleType("ok.util.logger")
class _ML:
    @staticmethod
    def get_logger(name):
        return logging.getLogger(name)
_ml.Logger = _ML
sys.modules["ok.util.logger"] = _ml

from ok.sandbox.sandbox_runner import SAFE_BUILTINS, BLOCKED_IMPORTS, create_restricted_builtins


class TestBuiltinRestriction(unittest.TestCase):

    def test_safe_builtins_included(self):
        builtins = create_restricted_builtins()
        self.assertIn("print", builtins)
        self.assertIn("len", builtins)
        self.assertIn("range", builtins)
        self.assertIn("int", builtins)
        self.assertIn("Exception", builtins)

    def test_dangerous_builtins_excluded(self):
        builtins = create_restricted_builtins()
        self.assertNotIn("open", builtins)
        self.assertNotIn("exec", builtins)
        self.assertNotIn("eval", builtins)
        self.assertNotIn("compile", builtins)
        # __import__ is present but replaced with the restricted version
        from ok.sandbox.sandbox_runner import _restricted_import
        self.assertIs(builtins["__import__"], _restricted_import)

    def test_blocked_imports(self):
        self.assertIn("os", BLOCKED_IMPORTS)
        self.assertIn("subprocess", BLOCKED_IMPORTS)
        self.assertIn("socket", BLOCKED_IMPORTS)
        self.assertIn("ctypes", BLOCKED_IMPORTS)
        self.assertIn("http", BLOCKED_IMPORTS)
        self.assertIn("sys", BLOCKED_IMPORTS)
        self.assertIn("importlib", BLOCKED_IMPORTS)

    def test_restricted_import_blocks_os(self):
        builtins = create_restricted_builtins()
        restricted_import = builtins["__import__"]
        with self.assertRaises(ImportError):
            restricted_import("os")

    def test_restricted_import_allows_allowed(self):
        builtins = create_restricted_builtins()
        restricted_import = builtins["__import__"]
        # math is not blocked
        import math
        result = restricted_import("math")
        self.assertEqual(result, math)


if __name__ == "__main__":
    unittest.main()
