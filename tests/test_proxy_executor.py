import logging
import multiprocessing
import os
import sys
import threading
import types
import unittest

# Stub ok package to avoid importing heavy GUI deps
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

from ok.feature.Box import Box
from ok.sandbox.ipc_protocol import IPCMessage, OP_CLICK, OP_GET_FRAME_SIZE, OP_FIND_FEATURE
from ok.sandbox.proxy_executor import ProxyExecutor


class TestProxyExecutor(unittest.TestCase):

    def _make_executor(self):
        request_q = multiprocessing.Queue()
        response_q = multiprocessing.Queue()
        executor = ProxyExecutor(request_q, response_q, shm_name=None, shm_size=0)
        return executor, request_q, response_q

    def _respond(self, response_q, request_id, op, result=None, error=None):
        resp = IPCMessage.response(request_id, op, result=result, error=error)
        response_q.put(resp.to_dict())

    def test_call_sends_request_and_gets_response(self):
        executor, req_q, resp_q = self._make_executor()

        def respond():
            d = req_q.get(timeout=5)
            self._respond(resp_q, d["id"], d["op"], result=True)

        t = threading.Thread(target=respond, daemon=True)
        t.start()
        result = executor._call(OP_CLICK, x=100, y=200)
        self.assertTrue(result)
        t.join(timeout=2)

    def test_call_propagates_error(self):
        executor, req_q, resp_q = self._make_executor()

        def respond():
            d = req_q.get(timeout=5)
            self._respond(resp_q, d["id"], d["op"], error="click failed")

        t = threading.Thread(target=respond, daemon=True)
        t.start()
        with self.assertRaises(Exception) as ctx:
            executor._call(OP_CLICK, x=100, y=200)
        self.assertIn("click failed", str(ctx.exception))
        t.join(timeout=2)

    def test_interaction_click(self):
        executor, req_q, resp_q = self._make_executor()

        def respond():
            d = req_q.get(timeout=5)
            self.assertEqual(d["op"], "interaction.click")
            self.assertEqual(d["kwargs"]["x"], 50)
            self.assertEqual(d["kwargs"]["y"], 75)
            self._respond(resp_q, d["id"], d["op"], result=True)

        t = threading.Thread(target=respond, daemon=True)
        t.start()
        executor.interaction.click(50, 75, move=True, down_time=0.02)
        t.join(timeout=2)

    def test_get_frame_size(self):
        executor, req_q, resp_q = self._make_executor()

        def respond():
            # width and height each trigger _refresh_size, so handle both
            for _ in range(2):
                d = req_q.get(timeout=5)
                self.assertEqual(d["op"], OP_GET_FRAME_SIZE)
                self._respond(resp_q, d["id"], d["op"],
                              result={"width": 1920, "height": 1080})

        t = threading.Thread(target=respond, daemon=True)
        t.start()
        w = executor.method.width
        h = executor.method.height
        self.assertEqual(w, 1920)
        self.assertEqual(h, 1080)
        t.join(timeout=2)

    def test_find_feature_returns_boxes(self):
        executor, req_q, resp_q = self._make_executor()
        box_dict = Box(10, 20, 100, 50, confidence=0.9, name="test").to_dict()

        def respond():
            d = req_q.get(timeout=5)
            self.assertEqual(d["op"], OP_FIND_FEATURE)
            self._respond(resp_q, d["id"], d["op"], result=[box_dict])

        t = threading.Thread(target=respond, daemon=True)
        t.start()
        result = executor.feature_set.find_feature(frame=None, feature_name="test")
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], Box)
        self.assertEqual(result[0].name, "test")
        t.join(timeout=2)

    def test_reset_scene(self):
        executor, req_q, resp_q = self._make_executor()

        def respond():
            d = req_q.get(timeout=5)
            self.assertEqual(d["op"], "reset_scene")
            self._respond(resp_q, d["id"], d["op"], result=True)

        t = threading.Thread(target=respond, daemon=True)
        t.start()
        result = executor.reset_scene(check_enabled=False)
        self.assertTrue(result)
        t.join(timeout=2)

    def test_ping(self):
        executor, req_q, resp_q = self._make_executor()

        def respond():
            d = req_q.get(timeout=5)
            self.assertEqual(d["op"], "ping")
            self._respond(resp_q, d["id"], d["op"], result="pong")

        t = threading.Thread(target=respond, daemon=True)
        t.start()
        result = executor.ping()
        self.assertEqual(result, "pong")
        t.join(timeout=2)

    def test_emit_notification(self):
        executor, req_q, resp_q = self._make_executor()

        def respond():
            d = req_q.get(timeout=5)
            self.assertEqual(d["op"], "emit_notification")
            self.assertEqual(d["kwargs"]["message"], "hello")
            self.assertEqual(d["kwargs"]["title"], "test")
            self._respond(resp_q, d["id"], d["op"], result=None)

        t = threading.Thread(target=respond, daemon=True)
        t.start()
        executor.emit_notification("hello", title="test")
        t.join(timeout=2)

    def test_emit_clear_box(self):
        executor, req_q, resp_q = self._make_executor()

        def respond():
            d = req_q.get(timeout=5)
            self.assertEqual(d["op"], "emit_clear_box")
            self._respond(resp_q, d["id"], d["op"], result=None)

        t = threading.Thread(target=respond, daemon=True)
        t.start()
        executor.emit_clear_box()
        t.join(timeout=2)

    def test_sleep(self):
        executor, req_q, resp_q = self._make_executor()

        def respond():
            d = req_q.get(timeout=5)
            self.assertEqual(d["op"], "sleep")
            self.assertEqual(d["kwargs"]["timeout"], 1.5)
            self._respond(resp_q, d["id"], d["op"], result=None)

        t = threading.Thread(target=respond, daemon=True)
        t.start()
        executor.sleep(1.5)
        t.join(timeout=2)

    def test_feature_exists(self):
        executor, req_q, resp_q = self._make_executor()

        def respond():
            d = req_q.get(timeout=5)
            self.assertEqual(d["op"], "feature_exists")
            self.assertEqual(d["kwargs"]["feature_name"], "my_button")
            self._respond(resp_q, d["id"], d["op"], result=True)

        t = threading.Thread(target=respond, daemon=True)
        t.start()
        result = executor.feature_set.feature_exists("my_button")
        self.assertTrue(result)
        t.join(timeout=2)

    def test_get_box_by_name(self):
        executor, req_q, resp_q = self._make_executor()
        box_dict = Box(5, 10, 30, 40, confidence=0.8, name="target").to_dict()

        def respond():
            d = req_q.get(timeout=5)
            self.assertEqual(d["op"], "get_box_by_name")
            self.assertEqual(d["kwargs"]["name"], "target")
            self._respond(resp_q, d["id"], d["op"], result=box_dict)

        t = threading.Thread(target=respond, daemon=True)
        t.start()
        result = executor.feature_set.get_box_by_name(frame=None, name="target")
        self.assertIsInstance(result, Box)
        self.assertEqual(result.name, "target")
        self.assertEqual(result.x, 5)
        self.assertEqual(result.y, 10)
        t.join(timeout=2)

    def test_get_box_by_name_returns_none(self):
        executor, req_q, resp_q = self._make_executor()

        def respond():
            d = req_q.get(timeout=5)
            self._respond(resp_q, d["id"], d["op"], result=None)

        t = threading.Thread(target=respond, daemon=True)
        t.start()
        result = executor.feature_set.get_box_by_name(frame=None, name="missing")
        self.assertIsNone(result)
        t.join(timeout=2)

    def test_interaction_swipe(self):
        executor, req_q, resp_q = self._make_executor()

        def respond():
            d = req_q.get(timeout=5)
            self.assertEqual(d["op"], "interaction.swipe")
            self.assertEqual(d["kwargs"]["from_x"], 0)
            self.assertEqual(d["kwargs"]["from_y"], 100)
            self.assertEqual(d["kwargs"]["to_x"], 500)
            self.assertEqual(d["kwargs"]["to_y"], 100)
            self.assertEqual(d["kwargs"]["duration"], 300)
            self._respond(resp_q, d["id"], d["op"], result=True)

        t = threading.Thread(target=respond, daemon=True)
        t.start()
        executor.interaction.swipe(0, 100, 500, 100, duration=300)
        t.join(timeout=2)

    def test_capture_method_connected(self):
        executor, _, _ = self._make_executor()
        self.assertTrue(executor.method.connected())


if __name__ == "__main__":
    unittest.main()
