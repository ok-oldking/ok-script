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
# Bringing the game in front: tries, and the wait after each for Windows to settle.
FRONT_ATTEMPTS = 3
FRONT_SETTLE = 0.1
# Standard dialog classes (message and error boxes) that other apps pop over the game.
DIALOG_CLASSES = ('#32770',)


class NotInFront(Exception):
    """The game window could not be brought in front, so input was not sent."""


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

    def bring_to_front(self, hwnd, point=None) -> bool:
        """Make sure the game window is in front, and that nothing covers ``point`` (screen
        coordinates), before input goes out. Dismisses dialog popups from other apps and
        raises the game; returns False when the game still is not in front."""
        if not hwnd:
            return False
        for _ in range(FRONT_ATTEMPTS):
            blocker = self._blocker(hwnd, point)
            if blocker is None:
                return True
            self._clear(hwnd, blocker, point)
            time.sleep(FRONT_SETTLE)
        blocker = self._blocker(hwnd, point)
        if blocker is None:
            return True
        self._log(f'game window is not in front, blocked by {self._describe(blocker)}')
        return False

    def _pid(self, hwnd):
        import win32process
        try:
            return win32process.GetWindowThreadProcessId(hwnd)[1]
        except Exception:
            return 0

    def _is_game(self, window, hwnd):
        """The game window or one of the game's own windows (its dialogs are game UI)."""
        return bool(window) and (window == hwnd or self._pid(window) == self._pid(hwnd))

    def _blocker(self, hwnd, point):
        """The window in the way of input to the game, or None. 0 means no foreground."""
        import win32con
        import win32gui
        foreground = win32gui.GetForegroundWindow()
        if not self._is_game(foreground, hwnd):
            return foreground
        if win32gui.IsIconic(hwnd):
            return 0
        if point is not None:
            try:
                under = win32gui.WindowFromPoint(point)
                root = win32gui.GetAncestor(under, win32con.GA_ROOT) if under else 0
            except Exception:
                root = 0
            if root and not self._is_game(root, hwnd):
                return root
        return None

    def _describe(self, window):
        import win32gui
        if not window:
            return 'nothing (no foreground window)'
        try:
            return f'{win32gui.GetClassName(window)!r} {win32gui.GetWindowText(window)!r}'
        except Exception:
            return str(window)

    def _dismissable(self, window):
        """A dialog popup from another app. Only standard dialogs are closed; anything else
        is left alone and the game is raised above it instead."""
        import win32gui
        try:
            return win32gui.IsWindowVisible(window) and win32gui.GetClassName(window) in DIALOG_CLASSES
        except Exception:
            return False

    def _clear(self, hwnd, blocker, point):
        import win32con
        import win32gui
        if blocker and self._dismissable(blocker):
            self._log(f'dismissing popup {self._describe(blocker)}')
            try:
                win32gui.PostMessage(blocker, win32con.WM_CLOSE, 0, 0)
            except Exception as e:
                self._log(f'could not close popup: {e}')
            time.sleep(FRONT_SETTLE)
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        except Exception as e:
            self._log(f'restore failed: {e}')
        if win32gui.GetForegroundWindow() != hwnd:
            # Windows only lets a process take the foreground right after input;
            # an Alt tap satisfies that rule inside this session.
            self.keyboard.press(self._keyboard_module.Key.alt)
            self.keyboard.release(self._keyboard_module.Key.alt)
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception as e:
                self._log(f'SetForegroundWindow failed: {e}')
        if self._blocker(hwnd, point) is None:
            return
        # Still covered (a topmost window, or the foreground was refused): lift the game
        # over other windows without leaving it topmost.
        flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
        try:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, flags)
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, flags)
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
        except Exception as e:
            self._log(f'raising the game failed: {e}')

    def _front(self, hwnd, x=-1, y=-1):
        """Input goes only to the game: bring it in front (with nothing over the target
        point) or raise NotInFront so the caller sees why nothing happened."""
        point = self._screen(hwnd, x, y) if x >= 0 and y >= 0 else None
        if not self.bring_to_front(hwnd, point):
            import win32gui
            raise NotInFront(f'game window is not in front '
                             f'(foreground: {self._describe(win32gui.GetForegroundWindow())})')

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
        self._front(hwnd, x, y)
        if x >= 0 and y >= 0:
            self._land(hwnd, x, y)
        button = self._button(key)
        self.mouse.press(button)
        time.sleep(max(down_time, 0.01))
        self.mouse.release(button)

    def mouse_down(self, hwnd, x=-1, y=-1, key='left'):
        self._front(hwnd, x, y)
        if x >= 0 and y >= 0:
            self._land(hwnd, x, y)
        self.mouse.press(self._button(key))

    def mouse_up(self, hwnd, key='left'):
        self.mouse.release(self._button(key))

    def move(self, hwnd, x, y):
        self._front(hwnd, x, y)
        self.mouse.position = self._screen(hwnd, x, y)

    def move_relative(self, hwnd, dx, dy):
        """Relative move (camera). Windows pointer acceleration scales it."""
        self._front(hwnd)
        self.mouse.move(int(dx), int(dy))

    def scroll(self, hwnd, x, y, amount):
        self._front(hwnd, x, y)
        if x >= 0 and y >= 0:
            self.mouse.position = self._screen(hwnd, x, y)
            time.sleep(0.01)
        sign = 1 if amount > 0 else -1
        for _ in range(abs(int(amount))):
            self.mouse.scroll(0, sign)
            time.sleep(0.001)

    def swipe(self, hwnd, from_x, from_y, to_x, to_y, duration=0.5, settle_time=0):
        self._front(hwnd, from_x, from_y)
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
        self._front(hwnd)
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
        self._front(hwnd)
        self.keyboard.type(str(text))
