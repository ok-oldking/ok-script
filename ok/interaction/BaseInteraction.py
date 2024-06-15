from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class BaseInteraction:

    def __init__(self, capture):
        self.capture = capture

    def should_capture(self):
        return True

    def send_key(self, key, down_time=0.02):
        pass

    def send_key_down(self, key):
        pass

    def send_key_up(self, key):
        pass

    def move(self, x, y):
        pass

    def swipe(self, from_x, from_y, to_x, to_y, duration):
        pass

    def move_relative(self, x, y):
        self.move(int(self.capture.width * x), int(self.capture.height * y))

    def click(self, x=-1, y=-1, name=None):
        if name is None:
            logger.debug(f"click {x, y}")
        else:
            logger.debug(f"click {name} {x, y}")
