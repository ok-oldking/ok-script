from ok.interaction.BaseInteraction import BaseInteraction
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class ADBBaseInteraction(BaseInteraction):

    def __init__(self, device_manager, capture, device_width, device_height):
        super().__init__(capture)
        self.device_manager = device_manager
        self.width = device_width
        self.height = device_height
        logger.info(f"width: {self.width}, height: {self.height}")
        if self.width == 0 or self.height == 0:
            logger.warning(f"Could not parse screen resolution.")
            # raise RuntimeError(f"ADBBaseInteraction: Could not parse screen resolution.")

    def send_key(self, key, down_time=0.02):
        super().send_key(key, down_time)
        self.device_manager.device.shell(f"input keyevent {key}")

    def swipe(self, from_x, from_y, to_x, to_y, duration):
        self.device_manager.device.shell(f"input swipe {from_x} {from_y} {to_x} {to_y} {duration}")

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01, move=True):
        super().click(x, y, name=name)
        x = int(x * self.width / self.capture.width)
        y = int(y * self.height / self.capture.height)
        self.device_manager.shell(f"input tap {x} {y}")
