# original https://github.com/Toufool/AutoSplit/blob/master/src/capture_method/WindowsGraphicsCaptureMethod.py
import numpy as np
from typing_extensions import override

from ok.capture.BaseCaptureMethod import BaseCaptureMethod
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class ADBCaptureMethod(BaseCaptureMethod):
    name = "ADB command line Capture"
    description = "use the adb screencap command, slow but works when in background/minimized, takes 300ms per frame"

    def __init__(self, device_manager, exit_event, width=0, height=0):
        super().__init__()
        self.exit_event = exit_event
        self._connected = (width != 0 and height != 0)
        self.device_manager = device_manager

    @override
    def do_get_frame(self) -> np.ndarray | None:
        return self.screencap()

    def screencap(self):
        if self.exit_event.is_set():
            return None
        frame = self.device_manager.do_screencap(self.device_manager.device)
        if frame is not None:
            self._connected = True
        else:
            self._connected = False
        return frame

    def connected(self):
        if not self._connected and self.device_manager.device is not None:
            self.screencap()
        return self._connected and self.device_manager.device is not None
