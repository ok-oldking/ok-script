"""Host-side client for the child-session agent."""

import socket
import threading
import time

import numpy as np

from ok.child_session import protocol
from ok.child_session.protocol import AgentError
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

CONNECT_TIMEOUT = 3
CALL_TIMEOUT = 15


class AgentClient:
    """Thread-safe connection to the agent of one project. Reconnects on demand."""

    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self._lock = threading.RLock()
        self._sock = None
        self._reader = None
        self._agent = None
        self.last_error = None

    def agent_info(self):
        """The agent's state file (port, pid, session, elevated), or None."""
        return protocol.read_json(protocol.agent_file(self.project_dir))

    def close(self):
        with self._lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                except OSError:
                    pass
            self._sock = None
            self._reader = None
            self._agent = None

    def _connect(self):
        info = self.agent_info()
        if not info or not info.get('port'):
            raise AgentError('child-session agent is not running')
        if self._sock is not None and self._agent == (info.get('pid'), info.get('port')):
            return
        self.close()
        try:
            sock = socket.create_connection((protocol.HOST, int(info['port'])), timeout=CONNECT_TIMEOUT)
        except OSError as e:
            raise AgentError(f'cannot reach the child-session agent: {e}') from e
        sock.settimeout(CALL_TIMEOUT)
        reader = sock.makefile('rb')
        protocol.send_message(sock, {'cmd': 'hello', 'token': info.get('token'),
                                     'version': protocol.PROTOCOL_VERSION})
        reply, _ = protocol.read_message(reader)
        if reply.get('error'):
            sock.close()
            raise AgentError(reply['error'])
        self._sock, self._reader = sock, reader
        self._agent = (info.get('pid'), info.get('port'))
        logger.info(f'connected to child-session agent pid={info.get("pid")} session={reply.get("session")} '
                    f'elevated={reply.get("elevated")}')

    def request(self, cmd: str, **kwargs):
        """Send one command; returns ``(reply, payload)``. Raises AgentError."""
        with self._lock:
            for attempt in (1, 2):
                try:
                    self._connect()
                    protocol.send_message(self._sock, dict(kwargs, cmd=cmd))
                    reply, payload = protocol.read_message(self._reader)
                    break
                except (OSError, ConnectionError, ValueError) as e:
                    self.close()
                    if attempt == 2:
                        self.last_error = str(e)
                        raise AgentError(f'child-session agent call {cmd} failed: {e}') from e
            if reply.get('error'):
                self.last_error = reply['error']
                raise AgentError(reply['error'])
            self.last_error = None
            return reply, payload

    def call(self, cmd: str, **kwargs) -> dict:
        return self.request(cmd, **kwargs)[0]

    def try_call(self, cmd: str, **kwargs):
        try:
            return self.call(cmd, **kwargs)
        except AgentError:
            return None

    def frame(self):
        reply, payload = self.request('frame')
        if not payload:
            return None
        return np.frombuffer(payload, np.uint8).reshape(reply['h'], reply['w'], 3)

    def wait_until_reachable(self, timeout: float, exit_event=None, cancelled=None) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if (exit_event is not None and exit_event.is_set()) or (cancelled and cancelled()):
                return False
            if self.try_call('ping') is not None:
                return True
            time.sleep(1)
        return False
