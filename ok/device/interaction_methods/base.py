import time

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

class BaseInteraction:

    KEY_LOG_INTERVAL = 1.0

    def __init__(self, capture):
        self.capture = capture
        self._last_key_log_times = {}

    def should_capture(self):
        return True

    def send_key(self, key, down_time=0.02):
        now = time.monotonic()
        last_log_time = self._last_key_log_times.get(key)
        if last_log_time is None or now - last_log_time >= self.KEY_LOG_INTERVAL:
            logger.debug(f'Sending key {key}')
            self._last_key_log_times[key] = now

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

    def back(self):
        self.send_key('esc')

    def scroll(self, x, y, scroll_amount):
        pass

    def on_destroy(self):
        pass
