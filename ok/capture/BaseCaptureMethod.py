import numpy as np

class CaptureException(Exception):
    pass

class BaseCaptureMethod:
    name = "None"
    description = ""
    last_captured_frame: np.ndarray
    top_cut = 0
    bottom_cut = 0
    left_cut = 0
    right_cut = 0
    width = 0
    height = 0

    def __init__(self):
        # Some capture methods don't need an initialization process
        pass

    def close(self):
        # Some capture methods don't need an initialization process
        pass

    def get_frame(self) -> np.ndarray | None:
        try:
            return self.do_get_frame()
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
