import numpy as np


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
        if self._size[0] == 0:
            self.get_frame()
        return self._size[0]

    @property
    def height(self):
        if self._size[1] == 0:
            self.get_frame()
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
            raise CaptureException() from e

    def do_get_frame(self):
        pass

    def draw_rectangle(self):
        pass

    def clickable(self):
        pass

    def connected(self):
        pass
