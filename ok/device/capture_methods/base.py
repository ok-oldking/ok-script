from ok.task.exceptions import CaptureException


class BaseCaptureMethod:
    name = "None"
    description = ""

    def __init__(self):
        self._size = (0, 0)
        self.exit_event = None

    def close(self):
        pass

    @property
    def width(self):
        self.measure_if_0()
        return self._size[0]

    @property
    def height(self):
        return self._size[1]

    def get_name(self):
        return self.name

    def measure_if_0(self):
        if self._size[0] == 0:
            self.get_frame()

    def get_frame(self):
        if self.exit_event.is_set():
            return
        try:
            frame = self.do_get_frame()
            if frame is not None:
                if frame.shape[0] <= 10 or frame.shape[1] <= 10:
                    return None
                self._size = (frame.shape[1], frame.shape[0])
                if frame.shape[2] == 4:
                    frame = frame[:, :, :3]
            return frame
        except Exception as e:
            raise CaptureException(str(e)) from e

    def __str__(self):
        return f'{self.get_name()}_{self.width}x{self.height}'

    def do_get_frame(self):
        pass

    def draw_rectangle(self):
        pass

    def clickable(self):
        pass

    def connected(self):
        pass



class BaseWindowsCaptureMethod(BaseCaptureMethod):

    def __init__(self, hwnd_window):
        super().__init__()
        self._hwnd_window = hwnd_window

    @property
    def hwnd_window(self):
        return self._hwnd_window

    @hwnd_window.setter
    def hwnd_window(self, hwnd_window):
        self._hwnd_window = hwnd_window

    def connected(self):
        return self._hwnd_window is not None and self._hwnd_window.exists and self._hwnd_window.hwnd > 0

    def get_abs_cords(self, x, y):
        return self._hwnd_window.get_abs_cords(x, y)

    def clickable(self):
        return self._hwnd_window is not None and self._hwnd_window.visible
