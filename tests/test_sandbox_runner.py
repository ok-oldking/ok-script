import logging
import os
import sys
import threading
import types
import unittest
from multiprocessing import Queue
from unittest.mock import MagicMock

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

from ok.sandbox.ipc_protocol import IPCMessage, OP_GET_FRAME_SIZE
from ok.sandbox.sandbox_runner import dispatch_request, IPCThread


class TestIPCDispatch(unittest.TestCase):

    def test_dispatch_click(self):
        mock_executor = MagicMock()
        mock_executor.interaction.click.return_value = None
        msg = IPCMessage.request("interaction.click", x=100, y=200, move=True,
                                 move_back=False, name=None, down_time=0.02, key="left")
        resp = dispatch_request(msg, mock_executor)
        self.assertIsNone(resp.error)
        mock_executor.interaction.click.assert_called_once_with(
            x=100, y=200, move=True, move_back=False, name=None,
            down_time=0.02, key="left")

    def test_dispatch_get_frame_size(self):
        mock_executor = MagicMock()
        mock_executor.method.width = 1920
        mock_executor.method.height = 1080
        msg = IPCMessage.request(OP_GET_FRAME_SIZE)
        resp = dispatch_request(msg, mock_executor)
        self.assertEqual(resp.result, {"width": 1920, "height": 1080})

    def test_dispatch_sleep(self):
        mock_executor = MagicMock()
        msg = IPCMessage.request("sleep", timeout=1.0)
        resp = dispatch_request(msg, mock_executor)
        self.assertIsNone(resp.error)
        self.assertTrue(resp.result)
        mock_executor.sleep.assert_called_once_with(1.0)

    def test_dispatch_error_handling(self):
        mock_executor = MagicMock()
        mock_executor.interaction.click.side_effect = Exception("click failed")
        msg = IPCMessage.request("interaction.click", x=0, y=0)
        resp = dispatch_request(msg, mock_executor)
        self.assertIn("click failed", resp.error)

    def test_dispatch_unknown_op(self):
        mock_executor = MagicMock()
        # Remove 'unknown_op_xyz' attribute if MagicMock auto-creates it
        del mock_executor.unknown_op_xyz
        msg = IPCMessage.request("unknown_op_xyz")
        resp = dispatch_request(msg, mock_executor)
        self.assertIn("Unknown operation", resp.error)


class TestIPCThread(unittest.TestCase):

    def test_ipc_thread_processes_request(self):
        request_q = Queue()
        response_q = Queue()
        mock_executor = MagicMock()
        mock_executor.interaction.click.return_value = None

        thread = IPCThread(request_q, response_q, mock_executor)
        thread.start()

        msg = IPCMessage.request("interaction.click", x=50, y=60)
        request_q.put(msg.to_dict())

        resp_dict = response_q.get(timeout=5)
        resp = IPCMessage.from_dict(resp_dict)
        self.assertEqual(resp.id, msg.id)
        self.assertIsNone(resp.error)
        self.assertTrue(resp.result)

        thread.stop()
        thread.join(timeout=3)

    def test_ipc_thread_stops(self):
        request_q = Queue()
        response_q = Queue()
        mock_executor = MagicMock()

        thread = IPCThread(request_q, response_q, mock_executor)
        thread.start()
        self.assertTrue(thread.is_alive())

        thread.stop()
        thread.join(timeout=3)
        self.assertFalse(thread.is_alive())


class TestSandboxRunnerSpawnShutdown(unittest.TestCase):

    def test_spawn_starts_ipc_thread(self):
        from ok.sandbox.sandbox_runner import SandboxRunner
        mock_executor = MagicMock()
        runner = SandboxRunner(mock_executor)

        # Mock Process to avoid actually spawning a child
        import ok.sandbox.sandbox_runner as sr_mod
        original_process = sr_mod.Process

        class FakeProcess:
            def __init__(self, *args, **kwargs):
                self.daemon = kwargs.get("daemon", False)
            def start(self):
                pass
            def is_alive(self):
                return False

        # Also mock shared_memory to avoid creating real shared memory
        original_shm = sr_mod.shared_memory.SharedMemory

        class FakeShm:
            def __init__(self, *a, **kw):
                self.name = "fake_shm"
            def close(self):
                pass
            def unlink(self):
                pass

        try:
            sr_mod.Process = FakeProcess
            sr_mod.shared_memory.SharedMemory = FakeShm

            runner.spawn()
            self.assertIsNotNone(runner._ipc_thread)
            self.assertTrue(runner._ipc_thread.is_alive())
            self.assertTrue(runner._running)

            runner.shutdown()
            self.assertFalse(runner._running)
        finally:
            sr_mod.Process = original_process
            sr_mod.shared_memory.SharedMemory = original_shm
            # Ensure cleanup of any running thread
            if runner._ipc_thread and runner._ipc_thread.is_alive():
                runner._ipc_thread.stop()
                runner._ipc_thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
