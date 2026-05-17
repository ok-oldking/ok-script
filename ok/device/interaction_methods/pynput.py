import time

from ok.device.capture_methods.base import BaseCaptureMethod
from ok.device.interaction_methods.base import BaseInteraction
from ok.util.logger import Logger
from ok.util.process import is_admin

logger = Logger.get_logger(__name__)

class PynputInteraction(BaseInteraction):
    KEY_MAP = {
        'lshift': 'shift_l',
        'rshift': 'shift_r',
        'lctrl': 'ctrl_l',
        'rctrl': 'ctrl_r',
        'lalt': 'alt_l',
        'ralt': 'alt_r',
        'lcontrol': 'ctrl_l',
        'rcontrol': 'ctrl_r',
        'return': 'enter',
        'pageup': 'page_up',
        'pagedown': 'page_down',
        'capslock': 'caps_lock',
        'numlock': 'num_lock',
        'scrolllock': 'scroll_lock',
        'printscreen': 'print_screen',
        'windows': 'cmd',
        'win': 'cmd',
        'command': 'cmd',
        'meta': 'cmd'
    }
    def __init__(self, capture: BaseCaptureMethod, hwnd_window):
        super().__init__(capture)
        self.hwnd_window = hwnd_window
        self.check_clickable = True
        if not is_admin():
            logger.error(f"You must be an admin to use PynputInteraction")

    def clickable(self):
        if self.check_clickable:
            return self.hwnd_window.is_foreground()
        else:
            return True

    def _parse_key(self, key):
        from pynput import keyboard
        if not isinstance(key, str):
            return key
        key_lower = key.lower()
        target_name = self.KEY_MAP.get(key_lower, key_lower)
        try:
            return keyboard.Key[target_name]
        except KeyError:
            return key

    def send_key(self, key, down_time=0.01):
        from pynput import keyboard
        if not self.clickable():
            logger.error(f"can't click on {key}, because capture is not clickable")
            return

        controller = keyboard.Controller()
        parsed_key = self._parse_key(str(key))
        controller.press(parsed_key)
        time.sleep(down_time)
        controller.release(parsed_key)

    def send_key_down(self, key):
        from pynput import keyboard
        if not self.clickable():
            logger.error(f"can't click on {key}, because capture is not clickable")
            return

        controller = keyboard.Controller()
        parsed_key = self._parse_key(str(key))
        controller.press(parsed_key)

    def send_key_up(self, key):
        from pynput import keyboard
        if not self.clickable():
            logger.error(f"can't click on {key}, because capture is not clickable")
            return

        controller = keyboard.Controller()
        parsed_key = self._parse_key(str(key))
        controller.release(parsed_key)

    def scroll(self, x, y, scroll_amount):
        from pynput import mouse
        if scroll_amount < 0:
            sign = -1
        elif scroll_amount > 0:
            sign = 1
        else:
            sign = 0
        logger.debug(f'pynput do_scroll {x}, {y}, {scroll_amount}')
        if not self.move(x, y):
            return
        time.sleep(0.001)

        controller = mouse.Controller()
        for i in range(abs(scroll_amount)):
            controller.scroll(0, sign)
            time.sleep(0.001)
        time.sleep(0.02)

    def move(self, x, y):
        from pynput import mouse
        if not self.clickable():
            return False

        abs_x, abs_y = self.capture.get_abs_cords(x, y)
        controller = mouse.Controller()
        controller.position = (abs_x, abs_y)
        if not self._verify_or_fallback_cursor_position(abs_x, abs_y):
            return False
        return True

    def _verify_or_fallback_cursor_position(self, abs_x, abs_y):
        """Verify pynput cursor movement and fall back to Win32 if it did not move."""
        try:
            import win32api

            current_x, current_y = win32api.GetCursorPos()
            if abs(current_x - abs_x) <= 1 and abs(current_y - abs_y) <= 1:
                return True

            logger.warning(
                f"pynput cursor move did not take effect, fallback to SetCursorPos: "
                f"target=({abs_x}, {abs_y}), current=({current_x}, {current_y})"
            )
            win32api.SetCursorPos((abs_x, abs_y))
            current_x, current_y = win32api.GetCursorPos()
            if abs(current_x - abs_x) <= 1 and abs(current_y - abs_y) <= 1:
                return True

            logger.error(
                f"cursor move failed after Win32 fallback: target=({abs_x}, {abs_y}), "
                f"current=({current_x}, {current_y}). If this was started by Windows Task "
                f"Scheduler, run it only when the user is logged on and keep the desktop unlocked."
            )
            return False
        except Exception as e:
            logger.error("cursor move verification failed", e)
            return True

    def swipe(self, x1, y1, x2, y2, duration, settle_time=0):
        from pynput import mouse
        x1, y1 = self.capture.get_abs_cords(x1, y1)
        x2, y2 = self.capture.get_abs_cords(x2, y2)

        controller = mouse.Controller()
        controller.position = (x1, y1)
        self._verify_or_fallback_cursor_position(x1, y1)
        time.sleep(0.1)

        controller.press(mouse.Button.left)

        dx = x2 - x1
        dy = y2 - y1

        steps = int(duration / 100)
        if steps <= 0:
            steps = 1

        step_dx = dx / steps
        step_dy = dy / steps

        for i in range(steps):
            controller.position = (x1 + int(i * step_dx), y1 + int(i * step_dy))
            time.sleep(0.01)
        controller.position = (x2, y2)
        self._verify_or_fallback_cursor_position(x2, y2)

        controller.release(mouse.Button.left)

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01, move=False, key="left"):
        from pynput import mouse
        super().click(x, y, name=name)
        if not self.clickable():
            logger.info(f"window in background, not clickable")
            return

        controller = mouse.Controller()
        current_pos = None
        if move_back:
            current_pos = controller.position

        if x != -1 and y != -1:
            abs_x, abs_y = self.capture.get_abs_cords(x, y)
            logger.info(f"left_click {abs_x, abs_y}")
            controller.position = (abs_x, abs_y)
            if not self._verify_or_fallback_cursor_position(abs_x, abs_y):
                return
            time.sleep(0.02)

        button = self.get_mouse_button(key)
        controller.press(button)
        time.sleep(down_time)
        controller.release(button)

        if current_pos:
            controller.position = current_pos
            self._verify_or_fallback_cursor_position(*current_pos)

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        from pynput import mouse
        if not self.clickable():
            logger.info(f"window in background, not clickable")
            return

        controller = mouse.Controller()
        if x != -1 and y != -1:
            abs_x, abs_y = self.capture.get_abs_cords(x, y)
            logger.info(f"mouse_down {abs_x, abs_y}")
            controller.position = (abs_x, abs_y)
            if not self._verify_or_fallback_cursor_position(abs_x, abs_y):
                return
            time.sleep(0.02)

        button = self.get_mouse_button(key)
        controller.press(button)

    def get_mouse_button(self, key):
        from pynput import mouse
        if key == "right":
            return mouse.Button.right
        if key == "middle":
            return mouse.Button.middle
        return mouse.Button.left

    def mouse_up(self, key="left"):
        from pynput import mouse
        if not self.clickable():
            logger.info(f"window in background, not clickable")
            return

        controller = mouse.Controller()
        button = self.get_mouse_button(key)
        controller.release(button)

    def should_capture(self):
        return self.clickable()

    def on_run(self):
        self.hwnd_window.bring_to_front()
