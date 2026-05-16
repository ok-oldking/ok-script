import cv2
import numpy as np

from ok.task.exceptions import CaptureException

from ok.device.capture_methods.base import BaseCaptureMethod

class ImageCaptureMethod(BaseCaptureMethod):
    name = "Image capture method "
    description = "for debugging"

    def __init__(self, exit_event, images):
        super().__init__()
        self.exit_event = exit_event
        self.set_images(images)
        self.index = 0

    def set_images(self, images):
        self.images = list(reversed(images))
        self.index = 0
        self.get_frame()

    def get_abs_cords(self, x, y):
        return x, y

    def do_get_frame(self):
        if len(self.images) > 0:
            image_path = self.images[self.index]
            if image_path:
                frame = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                if frame is None:
                    raise CaptureException(f'Cannot load image: {image_path}')
                if self.index < len(self.images) - 1:
                    self.index += 1
                return frame

    def connected(self):
        return True
