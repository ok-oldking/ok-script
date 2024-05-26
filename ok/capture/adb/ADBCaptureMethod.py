# original https://github.com/Toufool/AutoSplit/blob/master/src/capture_method/WindowsGraphicsCaptureMethod.py
import cv2
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
        self._size = (width, height)
        self._connected = (width != 0 and height != 0)
        self.device_manager = device_manager

    @property
    def width(self):
        if self._size[0] == 0:
            self.screencap()
        return self._size[0]

    @property
    def height(self):
        if self._size[1] == 0:
            self.screencap()
        return self._size[1]

    @override
    def do_get_frame(self) -> np.ndarray | None:
        return self.screencap()

    def screencap(self):
        if self.exit_event.is_set():
            return None
        frame = do_screencap(self.device_manager)
        if frame is not None:
            height, width, _ = frame.shape
            self._connected = True
            self._size = (width, height)
        else:
            self._connected = False
        return frame

    def connected(self):
        if not self._connected and self.device_manager.device is not None:
            self.screencap()
        return self._connected and self.device_manager.device is not None


def do_screencap(device_manager) -> np.ndarray | None:
    png_bytes = device_manager.shell("screencap -p", encoding=None)
    if png_bytes is not None and len(png_bytes) > 0:
        image_data = np.frombuffer(png_bytes, dtype=np.uint8)
        image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
        if image is not None:
            return image
        else:
            logger.error(f"Screencap image decode error, probably disconnected")
