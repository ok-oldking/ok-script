import asyncio
import time

from ok.device.interaction_methods.base import BaseInteraction
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

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
            "windows": "Meta",
            "command": "Meta",
            "cmd": "Meta",
            "cmd_l": "MetaLeft",
            "cmd_r": "MetaRight",
            "meta": "Meta",
            "alt": "Alt",
            "lalt": "Alt",
            "ralt": "Alt",
            "alt_l": "AltLeft",
            "alt_r": "AltRight",
            "alt_gr": "AltRight",
            "ctrl": "Control",
            "control": "Control",
            "lctrl": "Control",
            "rctrl": "Control",
            "lcontrol": "Control",
            "rcontrol": "Control",
            "ctrl_l": "ControlLeft",
            "ctrl_r": "ControlRight",
            "shift": "Shift",
            "lshift": "ShiftLeft",
            "rshift": "Shift",
            "shift_l": "ShiftLeft",
            "shift_r": "ShiftRight",
            "pageup": "PageUp",
            "pagedown": "PageDown",
            "page_up": "PageUp",
            "page_down": "PageDown",
            "capslock": "CapsLock",
            "caps_lock": "CapsLock",
            "numlock": "NumLock",
            "num_lock": "NumLock",
            "scrolllock": "ScrollLock",
            "scroll_lock": "ScrollLock",
            "printscreen": "PrintScreen",
            "print_screen": "PrintScreen",
            "delete": "Delete",
            "insert": "Insert",
            "home": "Home",
            "end": "End",
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

    def swipe(self, x1, y1, x2, y2, duration, settle_time=0):
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
