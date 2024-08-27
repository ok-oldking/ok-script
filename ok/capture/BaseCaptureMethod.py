import numpy as np

from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class CaptureException(Exception):
    pass


class BaseCaptureMethod:
    name = "None"
    description = ""
    _size = (0, 0)

    def __init__(self):
        # Some capture methods don't need an initialization process
        pass

    def close(self):
        # Some capture methods don't need an initialization process
        pass

    @property
    def width(self):
        return self._size[0]

    @property
    def height(self):
        return self._size[1]

    def get_frame(self) -> np.ndarray | None:
        try:
            frame = self.do_get_frame()
            if frame is not None:
                self._size = (frame.shape[1], frame.shape[0])
                if frame.shape[2] == 4:
                    frame = frame[:, :, :3]
            return frame
        except Exception as e:
            raise CaptureException(str(e)) from e

    def __str__(self):
        return f'{self.__class__.__name__}_{self.width}x{self.height}'

    def do_get_frame(self):
        pass

    def draw_rectangle(self):
        pass

    def clickable(self):
        pass

    def connected(self):
        pass
