import importlib
import time

from ok.device.capture_methods.base import BaseCaptureMethod
from ok.device.capture_methods.nemu_ipc import NemuIpcCaptureMethod
from ok.device.interaction_methods.base import BaseInteraction
from ok.device.interaction_methods.keys import ADB_KEY_MAP
from ok.device.interaction_methods.swipe import insert_swipe
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

class ADBInteraction(BaseInteraction):

    def __init__(self, device_manager, capture, device_width, device_height):
        super().__init__(capture)
        self.device_manager = device_manager
        self._u2 = None
        self._u2_device = None
        self.use_u2 = importlib.util.find_spec("uiautomator2")

    def send_key(self, key, down_time=0.02):
        key = ADB_KEY_MAP.get(str(key).lower(), key)
        self.device_manager.device.shell(f"input keyevent {key}")

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

    def swipe_nemu(self, from_x, from_y, to_x, to_y, duration, settle_time=0):
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

    def swipe_u2(self, from_x, from_y, to_x, to_y, duration, settle_time=0):
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

    def swipe(self, from_x, from_y, to_x, to_y, duration, settle_time=0):
        if isinstance(self.capture, NemuIpcCaptureMethod):
            self.swipe_nemu(from_x, from_y, to_x, to_y, duration, settle_time)
        elif self.use_u2:
            self.swipe_u2(from_x, from_y, to_x, to_y, duration, settle_time)
        else:
            self.device_manager.device.shell(
                f"input swipe {round(from_x)} {round(from_y)} {round(to_x)} {round(to_y)} {duration}")

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01, move=True, key=None):
        super().click(x, y, name=name)
        x = round(x)
        y = round(y)
        if isinstance(self.capture, NemuIpcCaptureMethod):
            self.capture.nemu_impl.click_nemu_ipc(x, y)
        else:
            self.device_manager.shell(f"input tap {x} {y}")

    def back(self):
        self.send_key('KEYCODE_BACK')
