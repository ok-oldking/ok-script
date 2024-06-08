import ctypes
import time

import pydirectinput

from ok.capture.BaseCaptureMethod import BaseCaptureMethod
from ok.interaction.BaseInteraction import BaseInteraction
from ok.logging.Logger import get_logger

logger = get_logger(__name__)

pydirectinput.FAILSAFE = False


class Win32Interaction(BaseInteraction):

    def __init__(self, capture: BaseCaptureMethod):
        super().__init__(capture)
        self.post = ctypes.windll.user32.PostMessageW
        if not is_admin():
            logger.error(f"You must be an admin to use Win32Interaction")

    def send_key(self, key, down_time=0.02):
        if not self.capture.clickable():
            return
        pydirectinput.keyDown(key)
        time.sleep(down_time)
        pydirectinput.keyUp(key)

    def move(self, x, y):
        if not self.capture.clickable():
            return
        x, y = self.capture.get_abs_cords(x, y)
        pydirectinput.moveTo(x, y)

    def swipe(self, x1, y1, x2, y2, duration):
        # Convert coordinates to integers
        x1, y1 = self.capture.get_abs_cords(x1, y1)
        x2, y2 = self.capture.get_abs_cords(x2, y2)

        # Move the mouse to the start point (x1, y1)
        pydirectinput.moveTo(x1, y1)
        time.sleep(0.1)  # Pause for a moment

        # Press the left mouse button down
        pydirectinput.mouseDown()

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
            pydirectinput.moveTo(x1 + int(i * step_dx), y1 + int(i * step_dy))
            time.sleep(0.1)  # Sleep for 10ms

        # Release the left mouse button
        pydirectinput.mouseUp()

    def click(self, x=-1, y=-1, move_back=False, name=None):
        super().click(x, y, name=name)
        if not self.capture.clickable():
            logger.info(f"window in background, not clickable")
            return
        # Convert the x, y position to lParam
        # lParam = win32api.MAKELONG(x, y)
        current_x, current_y = -1, -1
        if move_back:
            current_x, current_y = pydirectinput.position()
        if x != -1 and y != -1:
            x, y = self.capture.get_abs_cords(x, y)
            logger.info(f"left_click {x, y}")
            pydirectinput.moveTo(x, y)
        pydirectinput.click()
        if current_x != -1 and current_y != -1:
            pydirectinput.moveTo(current_x, current_y)

    def should_capture(self):
        return self.capture.clickable()


def is_admin():
    try:
        # Only Windows users with admin privileges can read the C drive directly
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False
