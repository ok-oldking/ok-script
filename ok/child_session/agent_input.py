"""Input inside the child session, with pynput (SendInput).

This module only runs in the agent, inside the child session. SendInput there goes to
the child session's own input queue, so the user's real mouse and keyboard are never
touched. The agent must be elevated when the game is elevated (UIPI silently drops
input from a normal process to an elevated window).

Coordinates are game client coordinates; they are converted to the child session's
screen coordinates here.
"""

import time

from ok.device.interaction_methods.keys import XBUTTON1, get_mouse_button, is_mouse_button

# Same names as ok.device.interaction_methods.pynput.PynputInteraction.KEY_MAP.
KEY_MAP = {
    'lshift': 'shift_l', 'rshift': 'shift_r', 'lctrl': 'ctrl_l', 'rctrl': 'ctrl_r',
    'lalt': 'alt_l', 'ralt': 'alt_r', 'lcontrol': 'ctrl_l', 'rcontrol': 'ctrl_r',
    'return': 'enter', 'pageup': 'page_up', 'pagedown': 'page_down', 'capslock': 'caps_lock',
    'numlock': 'num_lock', 'scrolllock': 'scroll_lock', 'printscreen': 'print_screen',
    'windows': 'cmd', 'win': 'cmd', 'command': 'cmd', 'meta': 'cmd',
}
# The game registers hover on a real cursor move before a press.
HOVER_SETTLE = 0.08


class Input:
    """Mouse and keyboard for the game window ``hwnd`` in this session."""

    def __init__(self, log=None):
        from pynput import keyboard, mouse
        self.mouse = mouse.Controller()
        self.keyboard = keyboard.Controller()
        self._mouse_module = mouse
        self._keyboard_module = keyboard
        self._log = log or (lambda *args: None)

    # --- helpers --------------------------------------------------------------

    def bring_to_front(self, hwnd) -> bool:
        import win32gui
        if not hwnd:
            return False
        if win32gui.GetForegroundWindow() == hwnd:
            return True
        # Windows only lets a process take the foreground right after input;
        # an Alt tap satisfies that rule inside this session.
        self.keyboard.press(self._keyboard_module.Key.alt)
        self.keyboard.release(self._keyboard_module.Key.alt)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception as e:
            self._log(f'SetForegroundWindow failed: {e}')
        return win32gui.GetForegroundWindow() == hwnd

    def _screen(self, hwnd, x, y):
        import win32gui
        return win32gui.ClientToScreen(hwnd, (int(x), int(y)))

    def _button(self, key):
        button = self._mouse_module.Button
        if is_mouse_button(key):
            return button.x1 if get_mouse_button(key) == XBUTTON1 else button.x2
        if key == 'right':
            return button.right
        if key == 'middle':
            return button.middle
        return button.left

    def _key(self, key):
        if not isinstance(key, str):
            return key
        if len(key) == 1:
            return key
        name = KEY_MAP.get(key.lower(), key.lower())
        try:
            return self._keyboard_module.Key[name]
        except KeyError:
            return key

    def _land(self, hwnd, x, y):
        sx, sy = self._screen(hwnd, x, y)
        self.mouse.position = (sx - 1, sy)
        time.sleep(0.02)
        self.mouse.position = (sx, sy)
        time.sleep(HOVER_SETTLE)

    # --- mouse ----------------------------------------------------------------

    def click(self, hwnd, x=-1, y=-1, key='left', down_time=0.05):
        self.bring_to_front(hwnd)
        if x >= 0 and y >= 0:
            self._land(hwnd, x, y)
        button = self._button(key)
        self.mouse.press(button)
        time.sleep(max(down_time, 0.01))
        self.mouse.release(button)

    def mouse_down(self, hwnd, x=-1, y=-1, key='left'):
        self.bring_to_front(hwnd)
        if x >= 0 and y >= 0:
            self._land(hwnd, x, y)
        self.mouse.press(self._button(key))

    def mouse_up(self, hwnd, key='left'):
        self.mouse.release(self._button(key))

    def move(self, hwnd, x, y):
        self.bring_to_front(hwnd)
        self.mouse.position = self._screen(hwnd, x, y)

    def move_relative(self, hwnd, dx, dy):
        """Relative move (camera). Windows pointer acceleration scales it."""
        self.bring_to_front(hwnd)
        self.mouse.move(int(dx), int(dy))

    def scroll(self, hwnd, x, y, amount):
        self.bring_to_front(hwnd)
        if x >= 0 and y >= 0:
            self.mouse.position = self._screen(hwnd, x, y)
            time.sleep(0.01)
        sign = 1 if amount > 0 else -1
        for _ in range(abs(int(amount))):
            self.mouse.scroll(0, sign)
            time.sleep(0.001)

    def swipe(self, hwnd, from_x, from_y, to_x, to_y, duration=0.5, settle_time=0):
        self.bring_to_front(hwnd)
        self._land(hwnd, from_x, from_y)
        self.mouse.press(self._button('left'))
        steps = max(int(duration / 0.01), 1)
        x1, y1 = self._screen(hwnd, from_x, from_y)
        x2, y2 = self._screen(hwnd, to_x, to_y)
        for i in range(1, steps + 1):
            self.mouse.position = (x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps)
            time.sleep(duration / steps)
        if settle_time:
            time.sleep(settle_time)
        self.mouse.release(self._button('left'))

    # --- keyboard -------------------------------------------------------------

    def key_down(self, hwnd, key):
        self.bring_to_front(hwnd)
        if is_mouse_button(key):
            self.mouse.press(self._button(key))
        else:
            self.keyboard.press(self._key(key))

    def key_up(self, hwnd, key):
        if is_mouse_button(key):
            self.mouse.release(self._button(key))
        else:
            self.keyboard.release(self._key(key))

    def send_key(self, hwnd, key, down_time=0.02):
        self.key_down(hwnd, key)
        time.sleep(max(down_time, 0.01))
        self.key_up(hwnd, key)

    def input_text(self, hwnd, text):
        self.bring_to_front(hwnd)
        self.keyboard.type(str(text))
