import asyncio
import ctypes
import importlib
import time

import numpy as np
import pydirectinput
import win32api
import win32gui

from ok.capture.adb.minitouch import random_normal_distribution, random_theta, random_rho
from ok.device.capture import NemuIpcCaptureMethod, BaseCaptureMethod
from ok.util.logger import Logger
from ok.util.process import is_admin

logger = Logger.get_logger(__name__)


class BaseInteraction:

    def __init__(self, capture):
        self.capture = capture

    def should_capture(self):
        return True

    def send_key(self, key, down_time=0.02):
        logger.debug(f'Sending key {key}')

    def send_key_down(self, key):
        pass

    def send_key_up(self, key):
        pass

    def move(self, x, y):
        pass

    def swipe(self, from_x, from_y, to_x, to_y, duration, settle_time=0):
        pass

    def click(self, x=-1, y=-1, move_back=False, name=None, move=move, down_time=0.05, key="left"):
        pass

    def on_run(self):
        pass

    def input_text(self, text):
        pass

    def back(self, after_sleep=0):
        self.send_key('esc')
        if after_sleep > 0:
            time.sleep(after_sleep)

    def scroll(self, x, y, scroll_amount):
        pass

    def on_destroy(self):
        pass


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
        pydirectinput.keyDown(str(key))
        time.sleep(down_time)
        pydirectinput.keyUp(str(key))

    def send_key_down(self, key):
        if not self.clickable():
            logger.error(f"can't click on {key}, because capture is not clickable")
            return
        pydirectinput.keyDown(str(key))

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
        pydirectinput.keyUp(str(key))

    def move(self, x, y):
        import mouse
        if not self.clickable():
            return
        x, y = self.capture.get_abs_cords(x, y)
        mouse.move(x, y)

    def swipe(self, x1, y1, x2, y2, duration, after_sleep=0.1, settle_time=0):
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
        if after_sleep > 0:
            time.sleep(after_sleep)
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


class PynputInteraction(BaseInteraction):

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
        try:
            return keyboard.Key[key.lower()]
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
        self.move(x, y)
        time.sleep(0.001)

        controller = mouse.Controller()
        for i in range(abs(scroll_amount)):
            controller.scroll(0, sign)
            time.sleep(0.001)
        time.sleep(0.02)

    def move(self, x, y):
        from pynput import mouse
        if not self.clickable():
            return

        abs_x, abs_y = self.capture.get_abs_cords(x, y)
        controller = mouse.Controller()
        controller.position = (abs_x, abs_y)

    def swipe(self, x1, y1, x2, y2, duration, after_sleep=0.1, settle_time=0):
        from pynput import mouse
        x1, y1 = self.capture.get_abs_cords(x1, y1)
        x2, y2 = self.capture.get_abs_cords(x2, y2)

        controller = mouse.Controller()
        controller.position = (x1, y1)
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

        if after_sleep > 0:
            time.sleep(after_sleep)

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
            time.sleep(0.02)

        button = self.get_mouse_button(key)
        controller.press(button)
        time.sleep(down_time)
        controller.release(button)

        if current_pos:
            controller.position = current_pos

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


# can interact with background windows, some games support it, like wuthering waves
class PostMessageInteraction(BaseInteraction):

    def __init__(self, capture: BaseCaptureMethod, hwnd_window):
        super().__init__(capture)
        self.hwnd_window = hwnd_window
        self.mouse_pos = (0, 0)
        self.last_activate = 0
        self.activate_interval = 1
        self.lparam = 0x1e0001
        self.activated = False
        self.hwnd_window.visible_monitors.append(self)

    @property
    def hwnd(self):
        return self.hwnd_window.hwnd

    def on_visible(self, visible):
        if visible:
            self.activated = False

    def send_key(self, key, down_time=0.01):
        super().send_key(key, down_time)
        self.send_key_down(key)
        time.sleep(down_time)
        self.send_key_up(key)

    def send_key_down(self, key, activate=True):
        if activate:
            self.try_activate()
        vk_code = self.get_key_by_str(key)
        lparam = self.make_lparam(vk_code, is_up=False)
        self.post(win32con.WM_KEYDOWN, vk_code, lparam)

    def send_key_up(self, key):
        # logger.debug(f'send_key_up {key}')
        vk_code = self.get_key_by_str(key)
        lparam = self.make_lparam(vk_code, is_up=True)
        self.post(win32con.WM_KEYUP, vk_code, lparam)

    def make_lparam(self, vk_code, is_up=False):
        scan_code = win32api.MapVirtualKey(vk_code, 0)
        lparam = (scan_code << 16) | 1
        if is_up:
            lparam |= (1 << 30) | (1 << 31)
        return lparam

    def get_key_by_str(self, key):
        key = str(key)
        if key_code := vk_key_dict.get(key.upper()):
            vk_code = key_code
        else:
            vk_code = win32api.VkKeyScan(key)
        return vk_code

    def input_text(self, text, activate=True):
        if activate:
            self.try_activate()
        for c in text:
            self.post(win32con.WM_CHAR,
                      ord(c), 0)
            time.sleep(0.01)

    def move(self, x, y, down_btn=0):
        long_pos = self.update_mouse_pos(x, y, True)
        self.post(win32con.WM_MOUSEMOVE, down_btn, long_pos)

    def scroll(self, x, y, scroll_amount):
        self.try_activate()
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

    def swipe(self, x1, y1, x2, y2, duration=3, after_sleep=0.1, settle_time=0):
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
            time.sleep(0.01)  # Sleep for 10ms
        if after_sleep > 0:
            time.sleep(after_sleep)
        # Release the left mouse button
        self.mouse_up()

    def activate(self):
        self.post(win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)

    def deactivate(self):
        self.post(win32con.WM_ACTIVATE, win32con.WA_INACTIVE, 0)

    def try_activate(self):
        if not self.activated:
            if not self.hwnd_window.is_foreground():
                self.activated = True
                self.activate()

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01, move=True, key="left"):
        super().click(x, y, name=name)
        if move:
            self.move(x, y)
            time.sleep(down_time)
        long_position = self.update_mouse_pos(x, y, activate=not move)

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

        self.post(btn_down, btn_mk, long_position
                  )
        time.sleep(down_time)
        self.post(btn_up, 0, long_position
                  )

    def right_click(self, x=-1, y=-1, move_back=False, name=None):
        super().right_click(x, y, name=name)
        long_position = self.update_mouse_pos(x, y)
        self.post(win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, long_position)
        self.post(win32con.WM_RBUTTONUP, 0, long_position)

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        long_position = self.update_mouse_pos(x, y)
        if key == "left":
            action = win32con.WM_LBUTTONDOWN
            btn = win32con.MK_LBUTTON
        elif key == "middle":
            action = win32con.WM_MBUTTONDOWN
            btn = win32con.MK_MBUTTON
        else:
            action = win32con.WM_RBUTTONDOWN
            btn = win32con.MK_RBUTTON
        self.post(action, btn, long_position)

    def update_mouse_pos(self, x, y, activate=True):
        self.try_activate()
        if x == -1 or y == -1:
            x, y = self.mouse_pos
        else:
            self.mouse_pos = (x, y)
        # logger.debug(f'mouse_pos: {x, y}')
        return win32api.MAKELONG(x, y)

    def mouse_up(self, key="left"):
        if key == "left":
            action = win32con.WM_LBUTTONUP
        elif key == "middle":
            action = win32con.WM_MBUTTONUP
        else:
            action = win32con.WM_RBUTTONUP
        self.post(action, 0,
                  win32api.MAKELONG(self.mouse_pos[0], self.mouse_pos[1]))

    def should_capture(self):
        return True


import win32con

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
    'ALT': win32con.VK_MENU,
    'LALT': win32con.VK_LMENU,
    'CONTROL': win32con.VK_CONTROL,
    'LCONTROL': win32con.VK_LCONTROL,
    'SHIFT': win32con.VK_SHIFT,
    'LSHIFT': win32con.VK_LSHIFT,
    'TAB': win32con.VK_TAB,
    'ENTER': win32con.VK_RETURN,
    'SPACE': win32con.VK_SPACE,
    'LEFT': win32con.VK_LEFT,
    'UP': win32con.VK_UP,
    'RIGHT': win32con.VK_RIGHT,
    'DOWN': win32con.VK_DOWN,
    # Add more keys as needed
}


class DoNothingInteraction(BaseInteraction):
    pass


class BrowserInteraction(BaseInteraction):
    def __init__(self, capture):
        super().__init__(capture)
        # We don't access self.page directly for calls, we go through capture.run_in_loop
        self.key_map = {
            "esc": "Escape",
            "return": "Enter",
            "enter": "Enter",
            "space": "Space",
            "backspace": "Backspace",
            "tab": "Tab",
            "left": "ArrowLeft",
            "right": "ArrowRight",
            "up": "ArrowUp",
            "down": "ArrowDown",
            "win": "Meta",
            "command": "Meta"
        }

    def _map_key(self, key):
        key_str = str(key).lower()
        if len(key_str) == 1:
            return key_str
        return self.key_map.get(key_str, key_str.title())

    def _run_action(self, action_coro):
        """Helper to run action on the capture's loop."""
        if hasattr(self.capture, 'run_in_loop'):
            self.capture.run_in_loop(action_coro)

    def send_key(self, key, down_time=0.02):
        mapped_key = self._map_key(key)
        logger.debug(f'BrowserInteraction send_key {key}')

        async def _act():
            await self.capture.page.keyboard.press(mapped_key, delay=down_time * 1000)

        self._run_action(_act())

    def send_key_down(self, key):
        mapped_key = self._map_key(key)

        async def _act():
            await self.capture.page.keyboard.down(mapped_key)

        self._run_action(_act())

    def send_key_up(self, key):
        mapped_key = self._map_key(key)

        async def _act():
            await self.capture.page.keyboard.up(mapped_key)

        self._run_action(_act())

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        button = "left"
        if key == "right":
            button = "right"
        elif key == "middle":
            button = "middle"

        async def _act():
            if x != -1 and y != -1:
                await self.capture.page.mouse.move(x, y)
            await self.capture.page.mouse.down(button=button)

        self._run_action(_act())

    def mouse_up(self, key="left"):
        button = "left"
        if key == "right":
            button = "right"
        elif key == "middle":
            button = "middle"

        async def _act():
            await self.capture.page.mouse.up(button=button)

        self._run_action(_act())

    def move(self, x, y):
        async def _act():
            await self.capture.page.mouse.move(x, y)

        self._run_action(_act())

    def scroll(self, x, y, scroll_amount):
        pixel_amount = scroll_amount * 100 * -1

        async def _act():
            if x != -1 and y != -1:
                await self.capture.page.mouse.move(x, y)
            await self.capture.page.mouse.wheel(0, pixel_amount)

        self._run_action(_act())
        time.sleep(0.02)

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01, move=True, key="left"):
        # BaseInteraction logic skipped as we need specific async handling
        button = "left"
        if key == "right":
            button = "right"
        elif key == "middle":
            button = "middle"

        async def _act():
            if x != -1 and y != -1:
                await self.capture.page.mouse.click(x, y, button=button, delay=down_time * 1000)
            else:
                await self.capture.page.mouse.down(button=button)
                await asyncio.sleep(down_time)
                await self.capture.page.mouse.up(button=button)

        self._run_action(_act())

    def input_text(self, text):
        async def _act():
            await self.capture.page.keyboard.type(text)

        self._run_action(_act())

    def swipe(self, x1, y1, x2, y2, duration, after_sleep=0.1, settle_time=0):
        async def _act():
            await self.capture.page.mouse.move(x1, y1)
            await self.capture.page.mouse.down()

            steps = max(int(duration / 20), 5)
            dx = (x2 - x1) / steps
            dy = (y2 - y1) / steps

            for i in range(steps):
                await self.capture.page.mouse.move(x1 + dx * i, y1 + dy * i)
                await asyncio.sleep(duration / 1000 / steps)

            await self.capture.page.mouse.move(x2, y2)
            if settle_time > 0:
                await asyncio.sleep(settle_time)
            await self.capture.page.mouse.up()

        self._run_action(_act())
        if after_sleep > 0:
            time.sleep(after_sleep)


class ADBInteraction(BaseInteraction):

    def __init__(self, device_manager, capture, device_width, device_height):
        super().__init__(capture)
        self.device_manager = device_manager
        self._u2 = None
        self._u2_device = None
        self.use_u2 = importlib.util.find_spec("uiautomator2")

    def send_key(self, key, down_time=0.02, after_sleep=0):
        self.device_manager.device.shell(f"input keyevent {key}")
        if after_sleep > 0:
            time.sleep(after_sleep)

    def input_text(self, text):
        # Convert each character to its Unicode code point
        # unicode_code_points = [ord(char) for char in text]
        #
        # # Iterate over the Unicode code points and send input key events
        # for code_point in unicode_code_points:
        self.device_manager.shell(f"input text {text}")

    @property
    def u2(self):
        if self._u2 is None or self._u2_device != self.device_manager.device:
            logger.info(f'init u2 device')
            import uiautomator2
            self._u2_device = self.device_manager.device
            self._u2 = uiautomator2.connect(self._u2_device)
        return self._u2

    def swipe_nemu(self, from_x, from_y, to_x, to_y, duration, after_sleep=0.1, settle_time=0):
        p2 = (to_x, to_y)
        points = insert_swipe(p0=(from_x, from_y), p3=p2)

        for point in points:
            self.capture.nemu_impl.down(*point)
            time.sleep(0.010)

        start = time.time()
        while time.time() - start < settle_time:
            self.capture.nemu_impl.down(*p2)
            time.sleep(0.140)

        self.capture.nemu_impl.up()

        time.sleep(0.1)

    def swipe_u2(self, from_x, from_y, to_x, to_y, duration, after_sleep=0.1, settle_time=0):
        """
        Performs a swipe gesture using low-level touch events, allowing
        a pause ('settle_time') at the end point before lifting the touch.
        Note: The 'duration' parameter has limited effect on the actual
        movement speed when using basic touch.down/move/up events.
        The move itself is typically fast.
        Args:
            from_x (int): Starting X coordinate.
            from_y (int): Starting Y coordinate.
            to_x (int): Ending X coordinate.
            to_y (int): Ending Y coordinate.
            duration (float): Intended duration of the swipe (limited effect).
            settle_time (float): Seconds to pause at (to_x, to_y) before touch up.
        """
        # Touch down at the starting point
        self.u2.touch.down(from_x, from_y)
        # Optional small delay after touching down before starting move
        time.sleep(0.02)
        dx = to_x - from_x
        dy = to_y - from_y
        steps = int(max(abs(dx), abs(dy)) / 16)
        logger.debug(f'swipe steps: {steps}')
        for i in range(1, steps + 1):
            progress = i / steps
            current_x = int(from_x + dx * progress)
            current_y = int(from_y + dy * progress)
            self.u2.touch.move(current_x, current_y)
            # Sleep between steps (except potentially the last one before settle)
            if i < steps - 5:
                time.sleep(0.001)
            else:
                time.sleep(0.005)
        # Move to the ending point (move itself is usually quick)
        self.u2.touch.move(to_x, to_y)
        # Pause for settle_time seconds *before* lifting the finger
        if settle_time > 0:
            time.sleep(settle_time)
        # Lift the touch up at the ending point
        self.u2.touch.up(to_x, to_y)

    def swipe(self, from_x, from_y, to_x, to_y, duration, after_sleep=0.1, settle_time=0):
        if isinstance(self.capture, NemuIpcCaptureMethod):
            self.swipe_nemu(from_x, from_y, to_x, to_y, duration, after_sleep, settle_time)
        elif self.use_u2:
            self.swipe_u2(from_x, from_y, to_x, to_y, duration, after_sleep, settle_time)
        else:
            self.device_manager.device.shell(
                f"input swipe {round(from_x)} {round(from_y)} {round(to_x)} {round(to_y)} {duration}")
        if after_sleep > 0:
            time.sleep(after_sleep)

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01, move=True, key=None):
        super().click(x, y, name=name)
        x = round(x)
        y = round(y)
        if isinstance(self.capture, NemuIpcCaptureMethod):
            self.capture.nemu_impl.click_nemu_ipc(x, y)
        else:
            self.device_manager.shell(f"input tap {x} {y}")

    def back(self, after_sleep=0):
        self.send_key('KEYCODE_BACK', after_sleep=after_sleep)


# Define the MOUSEINPUT structure
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


# Define the INPUT structure
class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("mi", MOUSEINPUT)]


# Define the SendInput function
SendInput = ctypes.windll.user32.SendInput
SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
SendInput.restype = ctypes.c_uint


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

    def swipe(self, x1, y1, x2, y2, duration=3, after_sleep=0, settle_time=0.1):
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


class ForegroundPostMessageInteraction(GenshinInteraction):
    def __init__(self, capture: BaseCaptureMethod, hwnd_window):
        super().__init__(capture, hwnd_window)
        pydirectinput.FAILSAFE = False
        self.check_clickable = True
        if not is_admin():
            logger.error(f"You must be an admin to use Win32Interaction")

    def clickable(self):
        if self.check_clickable:
            return self.hwnd_window.is_foreground()
        else:
            return True

    def should_capture(self):
        return self.clickable()

    def on_run(self):
        self.hwnd_window.bring_to_front()


def insert_swipe(p0, p3, speed=15, min_distance=10):
    """
    Insert way point from start to end.
    First generate a cubic bézier curve

    Args:
        p0: Start point.
        p3: End point.
        speed: Average move speed, pixels per 10ms.
        min_distance:

    Returns:
        list[list[int]]: List of points.

    Examples:
        > insert_swipe((400, 400), (600, 600), speed=20)
        [[400, 400], [406, 406], [416, 415], [429, 428], [444, 442], [462, 459], [481, 478], [504, 500], [527, 522],
        [545, 540], [560, 557], [573, 570], [584, 582], [592, 590], [597, 596], [600, 600]]
    """
    p0 = np.array(p0)
    p3 = np.array(p3)

    # Random control points in Bézier curve
    distance = np.linalg.norm(p3 - p0)
    p1 = 2 / 3 * p0 + 1 / 3 * p3 + random_theta() * random_rho(distance * 0.1)
    p2 = 1 / 3 * p0 + 2 / 3 * p3 + random_theta() * random_rho(distance * 0.1)

    # Random `t` on Bézier curve, sparse in the middle, dense at start and end
    segments = max(int(distance / speed) + 1, 5)
    lower = random_normal_distribution(-85, -60)
    upper = random_normal_distribution(80, 90)
    theta = np.arange(lower + 0., upper + 0.0001, (upper - lower) / segments)
    ts = np.sin(theta / 180 * np.pi)
    ts = np.sign(ts) * abs(ts) ** 0.9
    ts = (ts - min(ts)) / (max(ts) - min(ts))

    # Generate cubic Bézier curve
    points = []
    prev = (-100, -100)
    for t in ts:
        point = p0 * (1 - t) ** 3 + 3 * p1 * t * (1 - t) ** 2 + 3 * p2 * t ** 2 * (1 - t) + p3 * t ** 3
        point = point.astype(int).tolist()
        if np.linalg.norm(np.subtract(point, prev)) < min_distance:
            continue

        points.append(point)
        prev = point

    # Delete nearing points
    if len(points[1:]):
        distance = np.linalg.norm(np.subtract(points[1:], points[0]), axis=1)
        mask = np.append(True, distance > min_distance)
        points = np.array(points)[mask].tolist()
        if len(points) <= 1:
            points = [p0, p3]
    else:
        points = [p0, p3]

    return points
