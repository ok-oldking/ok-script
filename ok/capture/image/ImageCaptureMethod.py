# original https://github.com/Toufool/AutoSplit/blob/master/src/capture_method/WindowsGraphicsCaptureMethod.py

import cv2
import numpy as np
from typing_extensions import override

from ok.capture.BaseCaptureMethod import BaseCaptureMethod
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class ImageCaptureMethod(BaseCaptureMethod):
    name = "Image capture method "
    description = "for debugging"

    def __init__(self, images):
        super().__init__()
        self.images = list(reversed(images))
        self.get_frame()  # fill size
        self.images = list(reversed(images))

    @override
    def do_get_frame(self) -> np.ndarray | None:
        if len(self.images) > 0:
            image_path = self.images.pop()
            if image_path:
                frame = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                return frame

    def connected(self):
        return True
