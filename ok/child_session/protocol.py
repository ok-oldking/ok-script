"""Wire format and shared files between the host and the child-session agent.

Each request is one JSON line. Each reply is one JSON line; when it has ``len`` > 0,
that many bytes of payload follow (a raw BGR frame). The first request on a connection
must be ``hello`` with the agent's token.

Both sessions belong to the same Windows user, so they share ``%LOCALAPPDATA%``:
- ``<key>.agent.json`` — written by the agent: port, token, pid, session, elevated.
- ``<key>.config.json`` — written by the host: game window and startup-app settings the
  agent needs before the host connects.
"""

import hashlib
import json
import os
import socket
import tempfile

PROTOCOL_VERSION = 1
HOST = '127.0.0.1'


class AgentError(Exception):
    """The agent replied with an error, or could not be reached."""


def state_dir() -> str:
    base = os.environ.get('LOCALAPPDATA') or tempfile.gettempdir()
    path = os.path.join(base, 'ok-script', 'child_session')
    os.makedirs(path, exist_ok=True)
    return path


def project_key(project_dir: str) -> str:
    normalized = os.path.normcase(os.path.abspath(project_dir))
    return hashlib.sha1(normalized.encode('utf-8')).hexdigest()[:12]


def agent_file(project_dir: str) -> str:
    return os.path.join(state_dir(), f'{project_key(project_dir)}.agent.json')


def config_file(project_dir: str) -> str:
    return os.path.join(state_dir(), f'{project_key(project_dir)}.config.json')


def read_json(path: str):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_json(path: str, data) -> None:
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def send_message(sock: socket.socket, message: dict, payload: bytes = None) -> None:
    if payload:
        message = dict(message, len=len(payload))
    data = json.dumps(message, ensure_ascii=False).encode('utf-8') + b'\n'
    sock.sendall(data + payload if payload else data)


def read_message(reader):
    """Read one reply from a binary file object; returns ``(message, payload)``."""
    line = reader.readline()
    if not line:
        raise ConnectionError('agent closed the connection')
    message = json.loads(line)
    length = int(message.get('len') or 0)
    payload = b''
    while len(payload) < length:
        chunk = reader.read(length - len(payload))
        if not chunk:
            raise ConnectionError('agent closed the connection during a payload')
        payload += chunk
    return message, payload
