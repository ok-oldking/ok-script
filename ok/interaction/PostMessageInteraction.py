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
        self.mouse_pos = (0, 0)

    @property
    def hwnd(self):
        return self.hwnd_window.hwnd

    def send_key(self, key, down_time=0.01):
        self.send_key_down(key)
        time.sleep(down_time)
        self.send_key_up(key)

    def send_key_down(self, key):
        logger.debug(f'send_key_down {key}')
        vk_code = self.get_key_by_str(key)
        self.post(self.hwnd, win32con.WM_KEYDOWN, vk_code, 0)

    def send_key_up(self, key):
        logger.debug(f'send_key_up {key}')
        vk_code = self.get_key_by_str(key)
        self.post(self.hwnd, win32con.WM_KEYUP, vk_code, 0)

    def get_key_by_str(self, key):
        key = str(key)
        if key.lower() == 'esc':
            vk_code = win32con.VK_ESCAPE
        else:
            vk_code = win32api.VkKeyScan(key)
        return vk_code

    def move(self, x, y):
        long_pos = self.update_mouse_pos(x, y)
        self.post(self.hwnd, win32con.WM_MOUSEMOVE, 0, long_pos)
        logger.debug(f'move {x, y}')

    def middle_click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01):
        super().middle_click(x, y, move_back, name, down_time)
        long_position = self.update_mouse_pos(x, y)
        win32gui.PostMessage(
            self.hwnd, win32con.WM_MBUTTONDOWN, win32con.MK_MBUTTON, long_position
        )
        time.sleep(down_time)
        win32gui.PostMessage(
            self.hwnd, win32con.WM_MBUTTONUP, win32con.MK_MBUTTON, long_position
        )
        logger.debug(f'middle click {long_position}')

    def swipe(self, x1, y1, x2, y2, duration):
        # x1, y1 = self.get_scaled_pos(x1), self.get_scaled_pos(y1)
        # x2, y2 = self.get_scaled_pos(x2), self.get_scaled_pos(y2)
        # self.move(x1, y1)
        # self.mouse_down(x1, y1)
        # steps = int(duration / 100)
        # step_dx = (x2 - x1) / steps
        # step_dy = (y2 - y1) / steps
        # for i in range(steps):
        #     self.move(x1 + int(i * step_dx), y1 + int(i * step_dy))
        #     time.sleep(0.1)
        # self.mouse_up(x2, y2)
        pass

    def activate(self):
        self.post(self.hwnd, win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01):
        super().click(x, y, name=name)
        long_position = self.update_mouse_pos(x, y)
        # self.move(x, y)
        win32gui.PostMessage(
            self.hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, long_position
        )
        time.sleep(down_time)
        win32gui.PostMessage(
            self.hwnd, win32con.WM_LBUTTONUP, 0, long_position
        )

    def right_click(self, x=-1, y=-1, move_back=False, name=None):
        super().right_click(x, y, name=name)
        long_position = self.update_mouse_pos(x, y)
        self.post(self.hwnd, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, long_position)

        self.post(self.hwnd, win32con.WM_RBUTTONUP, win32con.MK_RBUTTON, long_position)

    def mouse_down(self, x=-1, y=-1, name=None):
        long_position = self.update_mouse_pos(x, y)

        self.post(self.hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, long_position)

    def update_mouse_pos(self, x, y):
        self.activate()
        if x == -1 or y == -1:
            x, y = self.mouse_pos
        else:
            self.mouse_pos = (x, y)
        return win32api.MAKELONG(x, y)

    def mouse_up(self):
        self.post(self.hwnd, win32con.WM_LBUTTONUP, win32con.MK_LBUTTON,
                  win32api.MAKELONG(self.mouse_pos[0], self.mouse_pos[1]))

    def should_capture(self):
        return True
