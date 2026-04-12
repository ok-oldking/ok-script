"""Proxy executor that mirrors TaskExecutor API via IPC."""
import numpy as np
from multiprocessing import shared_memory
from threading import Event

from ok.feature.Box import Box
from ok.sandbox.ipc_protocol import (
    IPCMessage,
    OP_GET_FRAME, OP_GET_FRAME_SIZE,
    OP_FIND_FEATURE, OP_GET_BOX_BY_NAME, OP_FEATURE_EXISTS,
    OP_SLEEP, OP_RESET_SCENE,
    OP_GET_GLOBAL_CONFIG,
    OP_ADB_SHELL, OP_ADB_UI_DUMP,
    OP_GET_TASK_BY_CLASS,
    OP_EMIT_DRAW_BOX, OP_EMIT_SCREENSHOT, OP_EMIT_NOTIFICATION, OP_EMIT_CLEAR_BOX,
    OP_PING,
)

RESPONSE_TIMEOUT = 30


class ProxyInteraction:
    """Proxies executor.interaction calls through IPC."""

    def __init__(self, executor):
        self._exec = executor

    def click(self, x, y, move_back=False, name=None, move=True,
              down_time=0.02, key='left'):
        return self._exec._call("interaction.click", x=x, y=y,
                                move_back=move_back, name=name, move=move,
                                down_time=down_time, key=key)

    def mouse_down(self, x, y, name=None, key="left"):
        return self._exec._call("interaction.mouse_down", x=x, y=y, name=name, key=key)

    def mouse_up(self, key="left"):
        return self._exec._call("interaction.mouse_up", key=key)

    def swipe(self, from_x, from_y, to_x, to_y, duration=500, settle_time=0):
        return self._exec._call("interaction.swipe", from_x=from_x, from_y=from_y,
                                to_x=to_x, to_y=to_y, duration=duration,
                                settle_time=settle_time)

    def scroll(self, x, y, count):
        return self._exec._call("interaction.scroll", x=x, y=y, count=count)

    def send_key(self, key, down_time=0.02):
        return self._exec._call("interaction.send_key", key=key, down_time=down_time)

    def send_key_down(self, key):
        return self._exec._call("interaction.send_key_down", key=key)

    def send_key_up(self, key):
        return self._exec._call("interaction.send_key_up", key=key)

    def input_text(self, text):
        return self._exec._call("interaction.input_text", text=text)

    def move(self, x, y):
        return self._exec._call("interaction.move", x=x, y=y)

    def back(self, *args, **kwargs):
        return self._exec._call("interaction.back", args=args, kwargs=kwargs)

    def on_run(self):
        return self._exec._call("interaction.on_run")

    def should_capture(self):
        return True


class ProxyCaptureMethod:
    """Proxies executor.method (capture method) properties."""

    def __init__(self, executor):
        self._exec = executor
        self._width = 0
        self._height = 0

    @property
    def width(self):
        self._refresh_size()
        return self._width

    @property
    def height(self):
        self._refresh_size()
        return self._height

    def _refresh_size(self):
        result = self._exec._call(OP_GET_FRAME_SIZE)
        if result:
            self._width = result["width"]
            self._height = result["height"]

    def get_frame(self):
        return self._exec._get_frame()

    def connected(self):
        return True


class ProxyFeatureSet:
    """Proxies executor.feature_set calls through IPC."""

    def __init__(self, executor):
        self._exec = executor

    def find_feature(self, frame, feature_name=None, horizontal_variance=0,
                     vertical_variance=0, threshold=0, use_gray_scale=False,
                     x=-1, y=-1, to_x=-1, to_y=-1, width=-1, height=-1,
                     box=None, match_method=None, screenshot=False,
                     canny_lower=0, canny_higher=0, frame_processor=None,
                     template=None, mask_function=None, limit=0, target_height=0):
        box_dict = box.to_dict() if box else None
        result = self._exec._call(OP_FIND_FEATURE,
                                  feature_name=feature_name,
                                  horizontal_variance=horizontal_variance,
                                  vertical_variance=vertical_variance,
                                  threshold=threshold,
                                  use_gray_scale=use_gray_scale,
                                  x=x, y=y, to_x=to_x, to_y=to_y,
                                  width=width, height=height,
                                  box=box_dict, screenshot=screenshot,
                                  canny_lower=canny_lower, canny_higher=canny_higher,
                                  limit=limit, target_height=target_height)
        return [Box.from_dict(b) for b in (result or [])]

    def get_box_by_name(self, frame, name):
        result = self._exec._call(OP_GET_BOX_BY_NAME, name=name)
        return Box.from_dict(result) if result else None

    def feature_exists(self, feature_name):
        return self._exec._call(OP_FEATURE_EXISTS, feature_name=feature_name)


class ProxyDeviceManager:
    """Proxies executor.device_manager access."""

    def __init__(self, executor):
        self._exec = executor
        self.hwnd_window = None
        self.supported_ratio = None

    def get_preferred_device(self):
        return self._exec._call("device.get_preferred_device")

    def adb_ensure_in_front(self):
        return self._exec._call("device.adb_ensure_in_front")

    def adb_ui_dump(self):
        return self._exec._call(OP_ADB_UI_DUMP)

    def shell(self, *args, **kwargs):
        return self._exec._call(OP_ADB_SHELL, args=args, kwargs=kwargs)


class ProxyGlobalConfig:
    """Proxies executor.global_config access."""

    def __init__(self, executor):
        self._exec = executor

    def get_config(self, option):
        return self._exec._call(OP_GET_GLOBAL_CONFIG, option=option)


class ProxyExecutor:
    """
    Drop-in replacement for TaskExecutor that proxies all calls through IPC.
    User tasks interact with this as if it were the real executor.
    """

    def __init__(self, request_queue, response_queue, shm_name=None, shm_size=0):
        self._request_queue = request_queue
        self._response_queue = response_queue
        self._shm = None
        self._shm_size = shm_size
        if shm_name and shm_size > 0:
            self._shm = shared_memory.SharedMemory(name=shm_name, size=shm_size)
        self.interaction = ProxyInteraction(self)
        self.method = ProxyCaptureMethod(self)
        self.feature_set = ProxyFeatureSet(self)
        self.device_manager = ProxyDeviceManager(self)
        self.global_config = ProxyGlobalConfig(self)
        self.exit_event = Event()
        self.paused = False
        self.debug = False
        self.current_task = None
        self.scene = None
        self.current_scene = None
        self.trigger_tasks = []
        self.onetime_tasks = []
        self.config = {}

    def _call(self, op, **kwargs):
        """Send an IPC request and wait for the response."""
        msg = IPCMessage.request(op, **kwargs)
        self._request_queue.put(msg.to_dict())
        while True:
            resp_dict = self._response_queue.get(timeout=RESPONSE_TIMEOUT)
            resp = IPCMessage.from_dict(resp_dict)
            if resp.id == msg.id:
                if resp.error:
                    raise Exception(resp.error)
                return resp.result

    def _get_frame(self):
        """Get frame from shared memory."""
        result = self._call(OP_GET_FRAME)
        if result and self._shm:
            h, w, c = result["height"], result["width"], result["channels"]
            arr = np.frombuffer(self._shm.buf[:h * w * c], dtype=np.uint8)
            return arr.reshape((h, w, c))
        return None

    @property
    def frame(self):
        return self._get_frame()

    def next_frame(self):
        self.reset_scene()
        return self._get_frame()

    def sleep(self, timeout):
        return self._call(OP_SLEEP, timeout=timeout)

    def reset_scene(self, check_enabled=True):
        return self._call(OP_RESET_SCENE, check_enabled=check_enabled)

    # GUI proxies
    def emit_draw_box(self, name, boxes, color, frame=None, debug=True):
        box_dicts = [b.to_dict() if isinstance(b, Box) else b for b in (boxes or [])]
        self._call(OP_EMIT_DRAW_BOX, name=name, boxes=box_dicts, color=color, debug=debug)

    def emit_notification(self, message, title=None, error=False, tray=False,
                          show_tab=None, params=None):
        self._call(OP_EMIT_NOTIFICATION, message=message, title=title,
                   error=error, tray=tray, show_tab=show_tab, params=params)

    def emit_clear_box(self):
        self._call(OP_EMIT_CLEAR_BOX)

    def ping(self):
        return self._call(OP_PING)
