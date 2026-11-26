"""Capture and window state of a game running in a child session.

The capture itself runs in the agent inside the child session (Windows Graphics Capture);
frames arrive here over localhost TCP.
"""

import threading
import time

from ok.child_session.protocol import AgentError
from ok.device.capture_methods.base import BaseCaptureMethod
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

INFO_TTL = 1.0


class ChildSessionWindow:
    """Stands in for ``HwndWindow`` while the game runs in the child session.

    ``hwnd`` is 0 on the host on purpose: the game's window handle only exists in the
    child session, so host-side Win32 code must not act on it.
    """

    is_child_session = True

    def __init__(self, client, exit_event):
        self.client = client
        self.app_exit_event = exit_event
        self.hwnd = 0
        self.hwnds = None
        self.top_hwnd = 0
        self.exe_full_path = None
        self.pos_valid = True
        self.scaling = 1.0
        self.x = self.y = 0
        # HwndWindow fields read by start checks; the game's frame needs no host-side fixing.
        self.frame_aspect_ratio = 0
        self.frame_width = self.frame_height = 0
        self.real_x_offset = self.real_y_offset = 0
        self.title = None
        self._info = {}
        self._info_time = 0
        self._lock = threading.Lock()

    def info(self, refresh=False) -> dict:
        with self._lock:
            if refresh or time.monotonic() - self._info_time > INFO_TTL:
                try:
                    self._info = self.client.call('window_info')
                except AgentError as e:
                    logger.debug(f'child session window_info failed: {e}')
                    self._info = {}
                self._info_time = time.monotonic()
            return self._info

    def do_update_window_size(self):
        self.info(refresh=True)

    @property
    def exists(self) -> bool:
        return bool(self.info().get('exists'))

    @property
    def visible(self) -> bool:
        return self.exists

    @property
    def width(self) -> int:
        return int(self.info().get('width') or 0)

    @property
    def height(self) -> int:
        return int(self.info().get('height') or 0)

    window_width = width
    window_height = height

    @property
    def hwnd_title(self) -> str:
        return self.info().get('title') or ''

    @property
    def capture_target_signature(self):
        info = self.info()
        return info.get('hwnd'), info.get('width'), info.get('height')

    def is_foreground(self) -> bool:
        return bool(self.info().get('foreground'))

    def bring_to_front(self) -> bool:
        try:
            return bool(self.client.call('front').get('ok'))
        except AgentError as e:
            logger.warning(f'child session bring_to_front failed: {e}')
            return False

    @property
    def real_width(self) -> int:
        return self.width

    @property
    def real_height(self) -> int:
        return self.height

    def try_resize_to(self, resize_to) -> bool:
        return False

    def update_frame_size(self, width, height):
        pass

    def update_window(self, *args, **kwargs):
        pass

    def get_abs_cords(self, x, y):
        return x, y

    def stop(self):
        pass

    def __str__(self):
        info = self.info()
        return f'ChildSessionWindow(hwnd={info.get("hwnd")}, {info.get("width")}x{info.get("height")})'


class ChildSessionCaptureMethod(BaseCaptureMethod):
    name = 'Child Session'
    description = 'Windows Graphics Capture inside the child session'

    def __init__(self, client, window: ChildSessionWindow, exit_event):
        super().__init__()
        self.client = client
        self.hwnd_window = window
        self.exit_event = exit_event

    def do_get_frame(self):
        try:
            return self.client.frame()
        except AgentError as e:
            logger.debug(f'child session frame failed: {e}')
            return None

    def connected(self) -> bool:
        return self.hwnd_window.exists

    def clickable(self) -> bool:
        return self.hwnd_window.exists

    def get_abs_cords(self, x, y):
        return x, y
