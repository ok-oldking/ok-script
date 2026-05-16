import time

import pydirectinput

from ok.device.capture_methods.base import BaseCaptureMethod
from ok.device.interaction_methods.base import BaseInteraction
from ok.device.interaction_methods.keys import normalize_pydirect_key
from ok.util.logger import Logger
from ok.util.process import is_admin

logger = Logger.get_logger(__name__)

class PyDirectInteraction(BaseInteraction):

    def __init__(self, capture: BaseCaptureMethod, hwnd_window):
        super().__init__(capture)
        pydirectinput.FAILSAFE = False

        import ctypes
        if hasattr(pydirectinput, 'SendInput'):
            pydirectinput.SendInput.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_int]

        self.hwnd_window = hwnd_window
        self.check_clickable = True
        if not is_admin():
            logger.error(f"You must be an admin to use Win32Interaction")

    def clickable(self):
        if self.check_clickable:
            return self.hwnd_window.is_foreground()
        else:
            return True

    def send_key(self, key, down_time=0.01):
        if not self.clickable():
            logger.error(f"can't click on {key}, because capture is not clickable")
            return
        key = normalize_pydirect_key(key)
        pydirectinput.keyDown(key)
        time.sleep(down_time)
        pydirectinput.keyUp(key)

    def send_key_down(self, key):
        if not self.clickable():
            logger.error(f"can't click on {key}, because capture is not clickable")
            return
        pydirectinput.keyDown(normalize_pydirect_key(key))

    def scroll(self, x, y, scroll_amount):
        import mouse
        if scroll_amount < 0:
            sign = -1
        elif scroll_amount > 0:
            sign = 1
        else:
            sign = 0
        logger.debug(f'pydirect do_scroll {x}, {y}, {scroll_amount}')
        self.move(x, y)
        time.sleep(0.001)
        for i in range(abs(scroll_amount)):
            mouse.wheel(sign)
            time.sleep(0.001)
        time.sleep(0.02)

    def send_key_up(self, key):
        if not self.clickable():
            logger.error(f"can't click on {key}, because capture is not clickable")
            return
        pydirectinput.keyUp(normalize_pydirect_key(key))

    def move(self, x, y):
        import mouse
        if not self.clickable():
            return
        x, y = self.capture.get_abs_cords(x, y)
        mouse.move(x, y)

    def swipe(self, x1, y1, x2, y2, duration, settle_time=0):
        x1, y1 = self.capture.get_abs_cords(x1, y1)
        x2, y2 = self.capture.get_abs_cords(x2, y2)

        pydirectinput.moveTo(x1, y1)
        time.sleep(0.1)

        pydirectinput.mouseDown()

        dx = x2 - x1
        dy = y2 - y1

        steps = int(duration / 100)

        step_dx = dx / steps
        step_dy = dy / steps

        for i in range(steps):
            pydirectinput.moveTo(x1 + int(i * step_dx), y1 + int(i * step_dy))
            time.sleep(0.01)
        pydirectinput.mouseUp()

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01, move=False, key="left"):
        super().click(x, y, name=name)
        if not self.clickable():
            logger.info(f"window in background, not clickable")
            return
        current_x, current_y = -1, -1
        if move_back:
            current_x, current_y = pydirectinput.position()
        import mouse
        if x != -1 and y != -1:
            x, y = self.capture.get_abs_cords(x, y)
            logger.info(f"left_click {x, y}")
            mouse.move(x, y)
        mouse.click(key)
        if current_x != -1 and current_y != -1:
            mouse.move(current_x, current_y)

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        if not self.clickable():
            logger.info(f"window in background, not clickable")
            return
        if x != -1 and y != -1:
            x, y = self.capture.get_abs_cords(x, y)
            logger.info(f"left_click {x, y}")
            pydirectinput.moveTo(x, y)
        button = self.get_mouse_button(key)
        pydirectinput.mouseDown(button=button)

    def get_mouse_button(self, key):
        button = pydirectinput.LEFT if key == "left" else pydirectinput.RIGHT
        return button

    def mouse_up(self, key="left"):
        if not self.clickable():
            logger.info(f"window in background, not clickable")
            return
        button = self.get_mouse_button(key)
        pydirectinput.mouseUp(button=button)

    def should_capture(self):
        return self.clickable()

    def on_run(self):
        self.hwnd_window.bring_to_front()
