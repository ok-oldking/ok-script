import time

import win32api
import win32con
import win32gui

from ok.capture.BaseCaptureMethod import BaseCaptureMethod
from ok.interaction.BaseInteraction import BaseInteraction
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


# can interact with background windows, some games support it, like wuthering waves
class PostMessageInteraction(BaseInteraction):

    def __init__(self, capture: BaseCaptureMethod, hwnd_window):
        super().__init__(capture)
        self.hwnd_window = hwnd_window
        self.post = win32gui.PostMessage

    @property
    def hwnd(self):
        return self.hwnd_window.hwnd

    def send_key(self, key, down_time=0.01):
        self.send_key_down(key)
        time.sleep(down_time)
        self.send_key_up(key)

    def send_key_down(self, key):
        logger.debug(f'send_key_down {key}')
        vk_code = win32api.VkKeyScan(str(key))
        self.post(self.hwnd, win32con.WM_KEYDOWN, vk_code, 0)

    def send_key_up(self, key):
        vk_code = win32api.VkKeyScan(str(key))
        self.post(self.hwnd, win32con.WM_KEYUP, vk_code, 0)

    def move(self, x, y):
        # x, y = self.get_scaled_pos(x), self.get_scaled_pos(y)
        # lParam = win32api.MAKELONG(x, y)
        # self.post(self.hwnd, win32con.WM_MOUSEMOVE, 0, lParam)
        pass

    def swipe(self, x1, y1, x2, y2, duration):
        x1, y1 = self.get_scaled_pos(x1), self.get_scaled_pos(y1)
        x2, y2 = self.get_scaled_pos(x2), self.get_scaled_pos(y2)
        self.move(x1, y1)
        self.mouse_down(x1, y1)
        steps = int(duration / 100)
        step_dx = (x2 - x1) / steps
        step_dy = (y2 - y1) / steps
        for i in range(steps):
            self.move(x1 + int(i * step_dx), y1 + int(i * step_dy))
            time.sleep(0.1)
        self.mouse_up(x2, y2)

    def click(self, x=-1, y=-1, move_back=False, name=None):
        super().click(x, y, name=name)
        if x != -1 and y != -1:
            x, y = self.get_scaled_pos(x), self.get_scaled_pos(y)
            self.move(x, y)
        # lParam = win32api.MAKELONG(x, y)
        # self.post(self.hwnd, win32con.WM_MOUSEMOVE, win32con.MK_LBUTTON, lParam)
        # time.sleep(0.2)
        # self.post(self.hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
        # time.sleep(0.2)
        # self.post(self.hwnd, win32con.WM_LBUTTONUP, win32con.MK_LBUTTON, lParam)
        # x = x if isinstance(x, int) else int(x)
        # y = y if isinstance(y, int) else int(y)
        long_position = win32api.MAKELONG(x, y)
        win32gui.PostMessage(
            self.hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, long_position
        )  # 鼠标左键按下
        time.sleep(0.01)
        win32gui.PostMessage(
            self.hwnd, win32con.WM_LBUTTONUP, win32con.MK_LBUTTON, long_position
        )  # 鼠标左键抬起

    def right_click(self, x=-1, y=-1, move_back=False, name=None):
        super().right_click(x, y, name=name)
        if x != -1 and y != -1:
            x, y = self.get_scaled_pos(x), self.get_scaled_pos(y)
            self.move(x, y)
        self.post(self.hwnd, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, win32api.MAKELONG(x, y))
        self.post(self.hwnd, win32con.WM_RBUTTONUP, 0, win32api.MAKELONG(x, y))

    def mouse_down(self, x=-1, y=-1, name=None):
        if x != -1 and y != -1:
            x, y = self.get_scaled_pos(x), self.get_scaled_pos(y)
            self.move(x, y)
        self.post(self.hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, win32api.MAKELONG(x, y))

    def mouse_up(self, x, y):
        self.post(self.hwnd, win32con.WM_LBUTTONUP, win32con.MK_LBUTTON, win32api.MAKELONG(x, y))

    def should_capture(self):
        return True

    def get_scaled_pos(self, cords):
        # return int(cords / self.hwnd_window.scaling)
        return int(cords)
