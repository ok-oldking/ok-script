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
        self.mouse_pos = (0, 0)

    @property
    def hwnd(self):
        return self.hwnd_window.hwnd

    def send_key(self, key, down_time=0.01):
        self.send_key_down(key)
        time.sleep(down_time)
        self.send_key_up(key)

    def send_key_down(self, key):
        # logger.debug(f'send_key_down {key}')
        vk_code = self.get_key_by_str(key)
        self.post(win32con.WM_KEYDOWN, vk_code, 0)

    def send_key_up(self, key):
        # logger.debug(f'send_key_up {key}')
        vk_code = self.get_key_by_str(key)
        self.post(win32con.WM_KEYUP, vk_code, 0)

    def get_key_by_str(self, key):
        key = str(key)
        if key_code := vk_key_dict.get(key.upper()):
            vk_code = key_code
        else:
            vk_code = win32api.VkKeyScan(key)
        return vk_code

    def move(self, x, y, down_btn=0):
        long_pos = self.update_mouse_pos(x, y, True)
        self.post(win32con.WM_MOUSEMOVE, down_btn, long_pos)
        # logger.debug(f'move {x, y}')

    def middle_click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01):
        super().middle_click(x, y, move_back, name, down_time)
        long_position = self.update_mouse_pos(x, y)
        self.post(win32con.WM_MBUTTONDOWN, win32con.MK_MBUTTON, long_position
                  )
        time.sleep(down_time)
        self.post(
            win32con.WM_MBUTTONUP, win32con.MK_MBUTTON, long_position
        )

    def scroll(self, x, y, scroll_amount):
        # Calculate the wParam
        # Positive scroll_amount indicates scroll up, negative is scroll down
        logger.debug(f'scroll {x}, {y}, {scroll_amount}')
        if x > 0 and y > 0:
            long_position = self.update_mouse_pos(x, y)
        else:
            long_position = 0
        wParam = win32api.MAKELONG(0, win32con.WHEEL_DELTA * scroll_amount)
        # Send the WM_MOUSEWHEEL message
        self.post(win32con.WM_MOUSEWHEEL, wParam, long_position)

    def post(self, message, wParam=0, lParam=0):
        win32gui.PostMessage(self.hwnd, message, wParam, lParam)

    def swipe(self, x1, y1, x2, y2, duration=3):
        # Move the mouse to the start point (x1, y1)
        self.move(x1, y1)
        time.sleep(0.1)  # Pause for a moment

        # Press the left mouse button down
        self.mouse_down(x1, y1)

        # Calculate the relative movement (dx, dy)
        dx = x2 - x1
        dy = y2 - y1

        # Calculate the number of steps
        steps = int(duration / 100)  # 100 steps per second

        # Calculate the step size
        step_dx = dx / steps
        step_dy = dy / steps

        # Move the mouse to the end point (x2, y2) in small steps
        for i in range(steps):
            self.move(x1 + int(i * step_dx), y1 + int(i * step_dy), down_btn=win32con.MK_LBUTTON)
            time.sleep(0.1)  # Sleep for 10ms

        # Release the left mouse button
        self.mouse_up()

    def activate(self):
        self.post(win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01):
        super().click(x, y, name=name)
        self.move(x, y)
        long_position = self.update_mouse_pos(x, y, activate=False)
        # self.move(x, y)
        self.post(win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, long_position
                  )
        time.sleep(down_time)
        self.post(win32con.WM_LBUTTONUP, 0, long_position
                  )

    def right_click(self, x=-1, y=-1, move_back=False, name=None):
        super().right_click(x, y, name=name)
        long_position = self.update_mouse_pos(x, y)
        self.post(win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, long_position)
        self.post(win32con.WM_RBUTTONUP, 0, long_position)

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        long_position = self.update_mouse_pos(x, y)
        action = win32con.WM_LBUTTONDOWN if key == "left" else win32con.WM_RBUTTONDOWN
        btn = win32con.MK_LBUTTON if key == "left" else win32con.MK_RBUTTON
        self.post(action, btn, long_position)

    def update_mouse_pos(self, x, y, activate=True):
        if activate:
            self.activate()
        if x == -1 or y == -1:
            x, y = self.mouse_pos
        else:
            self.mouse_pos = (x, y)
        # logger.debug(f'mouse_pos: {x, y}')
        return win32api.MAKELONG(x, y)

    def mouse_up(self, key="left"):
        action = win32con.WM_LBUTTONUP if key == "left" else win32con.WM_RBUTTONUP
        self.post(action, 0,
                  win32api.MAKELONG(self.mouse_pos[0], self.mouse_pos[1]))

    def should_capture(self):
        return True


vk_key_dict = {
    'F1': win32con.VK_F1,
    'F2': win32con.VK_F2,
    'F3': win32con.VK_F3,
    'F4': win32con.VK_F4,
    'F5': win32con.VK_F5,
    'F6': win32con.VK_F6,
    'F7': win32con.VK_F7,
    'F8': win32con.VK_F8,
    'F9': win32con.VK_F9,
    'F10': win32con.VK_F10,
    'F11': win32con.VK_F11,
    'F12': win32con.VK_F12,
    'ESC': win32con.VK_ESCAPE,
    # Add more keys as needed
}
