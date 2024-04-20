# original https://github.com/Toufool/AutoSplit/blob/master/src/capture_method/WindowsGraphicsCaptureMethod.py
import cv2
import numpy as np
from adbutils import AdbError
from typing_extensions import override

from ok.capture.BaseCaptureMethod import BaseCaptureMethod
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class ADBCaptureMethod(BaseCaptureMethod):
    name = "ADB command line Capture"
    description = "use the adb screencap command, slow but works when in background/minimized, takes 300ms per frame"

    def __init__(self, device, exit_event, width=0, height=0):
        super().__init__()
        self.exit_event = exit_event
        self._size = (width, height)
        self.device = device

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
    def get_frame(self) -> np.ndarray | None:
        return self.screencap()

    def screencap(self):
        if self.exit_event.is_set():
            return None
        frame = do_screencap(self.device)
        if frame is not None:
            height, width, _ = frame.shape
            self._size = (width, height)
        return frame


def do_screencap(device) -> np.ndarray | None:
    if device is not None:
        try:
            png_bytes = device.shell("screencap -p", encoding=None)
            if png_bytes is not None and len(png_bytes) > 0:
                image_data = np.frombuffer(png_bytes, dtype=np.uint8)
                image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
                if image is not None:
                    return image
                else:
                    logger.error(f"Screencap image decode error, probably disconnected")
        except AdbError as e:
            logger.error(f"Device {device} error", e)
