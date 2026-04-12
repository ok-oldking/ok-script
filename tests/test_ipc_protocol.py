import importlib
import importlib.util
import logging
import os
import sys
import types
import unittest

# Prevent ok/__init__.py from running by replacing the ok package with a
# lightweight stub that preserves __path__ so submodules can still be found.
_ok_dir = os.path.join(os.path.dirname(__file__), "..", "ok")
_ok_dir = os.path.normpath(_ok_dir)
_stub_ok = types.ModuleType("ok")
_stub_ok.__path__ = [_ok_dir]
_stub_ok.__package__ = "ok"
_stub_ok.__file__ = os.path.join(_ok_dir, "__init__.py")
sys.modules["ok"] = _stub_ok

# Mock ok.util.logger (needed by Box.py)
_ok_util = types.ModuleType("ok.util")
_ok_util.__path__ = [os.path.join(_ok_dir, "util")]
_ok_util.__package__ = "ok.util"
sys.modules["ok.util"] = _ok_util
_stub_ok.util = _ok_util

_mock_logger_mod = types.ModuleType("ok.util.logger")
class _MockLogger:
    @staticmethod
    def get_logger(name):
        return logging.getLogger(name)
_mock_logger_mod.Logger = _MockLogger
sys.modules["ok.util.logger"] = _mock_logger_mod

# Now safe to import sandbox and feature modules
from ok.sandbox.ipc_protocol import IPCMessage, OP_CLICK, OP_GET_FRAME, CMD_RUN, CMD_SHUTDOWN
from ok.feature.Box import Box


class TestBoxSerialization(unittest.TestCase):
    def test_to_dict(self):
        box = Box(10, 20, 100, 50, confidence=0.95, name="test_box")
        d = box.to_dict()
        self.assertEqual(d["x"], 10)
        self.assertEqual(d["y"], 20)
        self.assertEqual(d["width"], 100)
        self.assertEqual(d["height"], 50)
        self.assertEqual(d["name"], "test_box")
        self.assertAlmostEqual(d["confidence"], 0.95)

    def test_from_dict(self):
        d = {"x": 10, "y": 20, "width": 100, "height": 50, "name": "test_box", "confidence": 0.95}
        box = Box.from_dict(d)
        self.assertEqual(box.x, 10)
        self.assertEqual(box.y, 20)
        self.assertEqual(box.width, 100)
        self.assertEqual(box.name, "test_box")

    def test_roundtrip(self):
        box = Box(100, 200, 300, 400, confidence=0.88, name="roundtrip")
        restored = Box.from_dict(box.to_dict())
        self.assertEqual(restored.x, box.x)
        self.assertEqual(restored.y, box.y)
        self.assertEqual(restored.width, box.width)
        self.assertEqual(restored.name, box.name)
        self.assertAlmostEqual(restored.confidence, box.confidence)

    def test_from_dict_none(self):
        self.assertIsNone(Box.from_dict(None))


class TestIPCMessage(unittest.TestCase):
    def test_request_creation(self):
        msg = IPCMessage.request(OP_CLICK, x=100, y=200)
        self.assertIsNotNone(msg.id)
        self.assertEqual(msg.type, "request")
        self.assertEqual(msg.op, OP_CLICK)
        self.assertEqual(msg.kwargs, {"x": 100, "y": 200})
        self.assertIsNone(msg.error)

    def test_response_success(self):
        msg = IPCMessage.request(OP_CLICK, x=100, y=200)
        resp = IPCMessage.response(msg.id, OP_CLICK, result=True)
        self.assertEqual(resp.id, msg.id)
        self.assertEqual(resp.type, "response")
        self.assertTrue(resp.result)
        self.assertIsNone(resp.error)

    def test_response_error(self):
        msg = IPCMessage.request(OP_GET_FRAME)
        resp = IPCMessage.response(msg.id, OP_GET_FRAME, error="no frame available")
        self.assertEqual(resp.error, "no frame available")

    def test_host_command(self):
        msg = IPCMessage.command(CMD_RUN, task_id="my_task")
        self.assertEqual(msg.type, "command")
        self.assertEqual(msg.op, CMD_RUN)
        self.assertEqual(msg.kwargs["task_id"], "my_task")

    def test_to_dict_from_dict(self):
        msg = IPCMessage.request(OP_CLICK, x=50, y=75)
        d = msg.to_dict()
        restored = IPCMessage.from_dict(d)
        self.assertEqual(restored.id, msg.id)
        self.assertEqual(restored.op, OP_CLICK)
        self.assertEqual(restored.kwargs, {"x": 50, "y": 75})


if __name__ == "__main__":
    unittest.main()
