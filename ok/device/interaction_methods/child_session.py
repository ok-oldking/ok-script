"""The ChildSession interaction: input for a game running in the child session.

Every call is forwarded to the agent, which performs it with pynput inside the child
session (``ok/child_session/agent_input.py``). Nothing here touches the host's mouse or
keyboard. Coordinates are game client coordinates.
"""

from ok.child_session.protocol import AgentError
from ok.device.interaction_methods.base import BaseInteraction
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


class ChildSessionInteraction(BaseInteraction):

    def __init__(self, capture, hwnd_window=None, client=None):
        super().__init__(capture)
        self.hwnd_window = hwnd_window
        self._client = client

    @property
    def client(self):
        """The agent client: given, from the ChildSession capture, or created on demand."""
        if self._client is None:
            self._client = getattr(self.capture, 'client', None)
        if self._client is None:
            from ok.child_session.client import AgentClient
            from ok.child_session.host import project_dir
            self._client = AgentClient(project_dir())
        return self._client

    @client.setter
    def client(self, value):
        self._client = value

    def _call(self, cmd, **kwargs):
        try:
            return self.client.call(cmd, **kwargs)
        except AgentError as e:
            logger.error(f'child session {cmd} failed: {e}')
            return None

    def should_capture(self):
        return True

    def click(self, x=-1, y=-1, move_back=False, name=None, move=True, down_time=0.05, key="left"):
        super().click(x, y, name=name)
        self._call('click', x=int(x), y=int(y), key=key, down_time=down_time)

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        self._call('mouse_down', x=int(x), y=int(y), key=key)

    def mouse_up(self, key="left"):
        self._call('mouse_up', key=key)

    def move(self, x, y):
        self._call('move', x=int(x), y=int(y))

    def move_relative(self, dx, dy):
        self._call('move_relative', dx=int(dx), dy=int(dy))

    def scroll(self, x, y, scroll_amount):
        self._call('scroll', x=int(x), y=int(y), amount=int(scroll_amount))

    def swipe(self, from_x, from_y, to_x, to_y, duration, settle_time=0):
        """``duration`` is in milliseconds, as tasks pass it."""
        self._call('swipe', from_x=int(from_x), from_y=int(from_y), to_x=int(to_x), to_y=int(to_y),
                   duration=float(duration) / 1000, settle_time=float(settle_time or 0))

    def send_key(self, key, down_time=0.02):
        super().send_key(key, down_time)
        self._call('send_key', key=str(key), down_time=down_time)

    def send_key_down(self, key):
        self._call('key_down', key=str(key))

    def send_key_up(self, key):
        self._call('key_up', key=str(key))

    def input_text(self, text):
        self._call('input_text', text=str(text))
