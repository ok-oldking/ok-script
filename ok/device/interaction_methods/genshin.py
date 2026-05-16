import ctypes
import time

import win32api
import win32con
import win32gui

from ok.device.capture_methods.base import BaseCaptureMethod
from ok.device.interaction_methods.base import BaseInteraction
from ok.device.interaction_methods.keys import vk_key_dict
from ok.device.interaction_methods.post_message import PostMessageInteraction
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]



class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("mi", MOUSEINPUT)]



SendInput = ctypes.windll.user32.SendInput



class GenshinInteraction(BaseInteraction):

    def __init__(self, capture: BaseCaptureMethod, hwnd_window):
        super().__init__(capture)
        self.post_interaction = PostMessageInteraction(capture, hwnd_window)
        self.hwnd_window = hwnd_window
        self.hwnd_window.visible_monitors.append(self)
        self.user32 = ctypes.windll.user32
        self.cursor_position = None

    @property
    def hwnd(self):
        return self.hwnd_window.hwnd

    def do_post_scroll(self, x, y, scroll_amount):
        # Calculate the wParam
        # Positive scroll_amount indicates scroll up, negative is scroll down
        logger.debug(f'scroll {x}, {y}, {scroll_amount}')
        if x > 0 and y > 0:
            long_position = self.make_mouse_position(x, y)
        else:
            long_position = 0
        wParam = win32api.MAKELONG(0, win32con.WHEEL_DELTA * scroll_amount)
        # Send the WM_MOUSEWHEEL message
        self.post(win32con.WM_MOUSEWHEEL, wParam, long_position)

    def do_send_key(self, key, down_time=0.02):
        vk_code = self.get_key_by_str(key)
        self.post(win32con.WM_KEYDOWN, vk_code, 0x1e0001)
        if down_time > 0.1:
            time.sleep(down_time)
        else:
            self.post(win32con.WM_CHAR, vk_code, 0x1e0001)
        self.post(win32con.WM_KEYUP, vk_code, 0xc01e0001)
        if down_time <= 0.1:
            time.sleep(down_time)
        else:
            time.sleep(0.02)

    def operate(self, fun, block=False):
        bg = not self.hwnd_window.is_foreground()
        result = None
        if bg:
            if block:
                self.block_input()
            self.cursor_position = win32api.GetCursorPos()
            self.activate()
        try:
            result = fun()
        except Exception as e:
            logger.error(f'operate exception', e)
        if bg:
            self.deactivate()
            time.sleep(0.02)
            win32api.SetCursorPos(self.cursor_position)
            if block:
                self.unblock_input()
        return result

    def send_key(self, key, down_time=0.02):
        logger.debug(f'GenshinInteraction send key {key} {down_time}')
        # self.do_send_key(key)
        self.operate(lambda: self.do_send_key(key, down_time))

    def block_input(self):
        self.user32.BlockInput(True)

    def unblock_input(self):
        self.user32.BlockInput(False)

    def send_key_down(self, key):
        current_position = win32api.GetCursorPos()
        self.post_interaction.activate()
        self.post_interaction.send_key_down(key)
        win32api.SetCursorPos(current_position)

    def do_send_key_down(self, key):
        vk_code = self.get_key_by_str(key)
        self.post(win32con.WM_KEYDOWN, vk_code, 0x1e0001)
        self.post(win32con.WM_CHAR, vk_code, 0x1e0001)

    def do_send_key_up(self, key):
        vk_code = self.get_key_by_str(key)
        self.post(win32con.WM_KEYUP, vk_code, 0xc01e0001)

    def send_key_up(self, key):
        logger.debug(f'send_key_up {key}')
        vk_code = self.get_key_by_str(key)
        self.deactivate()

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

    def middle_click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01):
        self.operate(lambda: self.do_middle_click(x, y, move_back, name, down_time))

    def do_scroll(self, x, y, scroll_amount):
        import mouse
        if scroll_amount < 0:
            sign = -1
        elif scroll_amount > 0:
            sign = 1
        else:
            sign = 0
        abs_x, abs_y = self.capture.get_abs_cords(x, y)
        click_pos = win32api.MAKELONG(x, y)
        logger.debug(f'do_scroll {x}, {y}, {click_pos} {scroll_amount}')
        win32api.SetCursorPos((abs_x, abs_y))
        time.sleep(0.1)
        for i in range(abs(scroll_amount)):
            mouse.wheel(sign)
            time.sleep(0.001)
        # mouse.wheel(scroll_amount)
        time.sleep(0.1)

    def scroll(self, x, y, scroll_amount):
        return self.operate(lambda: self.do_scroll(x, y, scroll_amount), block=True)

    def post(self, message, wParam=0, lParam=0):
        win32gui.PostMessage(self.hwnd, message, wParam, lParam)

    def swipe(self, x1, y1, x2, y2, duration=3, settle_time=0.1):
        # Move the mouse to the start point (x1, y1)
        logger.debug(f'genshin swipe start {x1, y1, x2, y2}')
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
            time.sleep(0.01)  # Sleep for 10ms
        if settle_time > 0:
            time.sleep(settle_time)
        # Release the left mouse button
        self.mouse_up()
        logger.debug(f'genshin swipe end {x1, y1, x2, y2}')

    def activate(self):
        logger.debug(f'GenshinInteraction activate {self.hwnd}')
        self.hwnd_window.to_handle_mute = False
        self.post_interaction.activate()

    def deactivate(self):
        logger.debug('GenshinInteraction deactivate')
        self.post_interaction.deactivate()
        self.hwnd_window.to_handle_mute = True

    def try_activate(self):
        if not self.hwnd_window.is_foreground():
            self.activate()

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.02, move=True, key="left"):
        self.operate(lambda: self.do_click(x, y, down_time=down_time, key=key), block=True)

    def do_middle_click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.02):
        self.do_click(x, y, move_back, name, down_time, key="middle")

    def do_click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.02, move=True, key="left"):
        click_pos = self.make_mouse_position(x, y)
        logger.debug(f'click {x}, {y}, {click_pos} {down_time}')
        if key == "left":
            btn_down = win32con.WM_LBUTTONDOWN
            btn_mk = win32con.MK_LBUTTON
            btn_up = win32con.WM_LBUTTONUP
        elif key == "middle":
            btn_down = win32con.WM_MBUTTONDOWN
            btn_mk = win32con.MK_MBUTTON
            btn_up = win32con.WM_MBUTTONUP
        else:
            btn_down = win32con.WM_RBUTTONDOWN
            btn_mk = win32con.MK_RBUTTON
            btn_up = win32con.WM_RBUTTONUP
        self.post(btn_down, btn_mk, click_pos
                  )
        self.post(btn_up, 0, click_pos
                  )
        time.sleep(down_time)

    def do_mouse_up(self, x=-1, y=-1, move_back=False, move=True, btn=None):
        if btn is None:
            btn = win32con.WM_LBUTTONUP
        elif btn == 'right':
            btn = win32con.WM_RBUTTONUP
        click_pos = win32api.MAKELONG(x, y)
        logger.debug(f'do_mouse_up {x}, {y}, {click_pos}')
        self.post(btn, 0, click_pos
                  )

    def right_click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.02):
        self.do_click(x, y, move_back, name, down_time, key="right")

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        self.operate(lambda: self.do_mouse_down(x, y, name, key))

    def do_mouse_down(self, x=-1, y=-1, name=None, key="left"):
        click_pos = self.make_mouse_position(x, y)
        action = win32con.WM_LBUTTONDOWN if key == "left" else win32con.WM_RBUTTONDOWN
        btn = win32con.MK_LBUTTON if key == "left" else win32con.MK_RBUTTON
        self.post(action, btn, click_pos
                  )

    def make_mouse_position(self, x, y):
        if x < 0:
            click_pos = win32api.MAKELONG(round(self.capture.width * 0.5), round(self.capture.height * 0.5))
        else:
            abs_x, abs_y = self.capture.get_abs_cords(x, y)
            click_pos = win32api.MAKELONG(x, y)
        if x >= 0:
            win32api.SetCursorPos((abs_x, abs_y))
            time.sleep(0.001)
        return click_pos

    def do_mouse_up(self, x=-1, y=-1, key="left"):
        click_pos = self.make_mouse_position(x, y)
        logger.debug(f'click {x}, {y}, {click_pos}')
        action = win32con.WM_LBUTTONUP if key == "left" else win32con.WM_RBUTTONUP
        self.post(action, 0, click_pos
                  )

    def update_mouse_pos(self, x, y, activate=True):
        self.try_activate()
        if x == -1 or y == -1:
            x, y = self.mouse_pos
        else:
            self.mouse_pos = (x, y)
        # logger.debug(f'mouse_pos: {x, y}')
        return win32api.MAKELONG(x, y)

    def mouse_up(self, x=-1, y=-1, key="left"):
        self.operate(lambda: self.do_mouse_up(x, y, key))

    def should_capture(self):
        return True

    def on_visible(self, visible):
        """
        Your custom function to be executed when the window becomes active.

        Args:
            hwnd: The handle of the window that became active.
        """
        logger.debug(f"on_visible {visible}")
        if visible:
            self.post_interaction.activate()

    def on_destroy(self):
        logger.info('GenshinInteraction on_destroy')
        self.hwnd_window.bring_to_front()
        self.activate()

    def move_mouse_relative(self, dx, dy):
        self.operate(lambda: self.do_move_mouse_relative(dx, dy), block=True)

    def do_move_mouse_relative(self, dx, dy):
        """
        Moves the mouse cursor relative to its current position using user32.SendInput.

        Args:
            dx: The number of pixels to move the mouse horizontally (positive for right, negative for left).
            dy: The number of pixels to move the mouse vertically (positive for down, negative for up).
        """

        mi = MOUSEINPUT(dx, dy, 0, 1, 0, None)
        i = INPUT(0, mi)  # type=0 indicates a mouse event
        SendInput(1, ctypes.pointer(i), ctypes.sizeof(INPUT))
