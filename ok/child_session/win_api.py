"""Windows session helpers for child sessions (ctypes, no admin needed unless noted)."""

import ctypes
import os
from ctypes import wintypes

NO_SESSION = 0xFFFFFFFF
_WTS_CONNECT_STATE = 14
_WTS_CLIENT_NAME = 10
_WTS_IS_REMOTE_SESSION = 29
_STATES = ('Active', 'Connected', 'ConnectQuery', 'Shadow', 'Disconnected', 'Idle', 'Listen', 'Reset', 'Down',
           'Init')
BS = chr(92)


def _wts():
    return ctypes.WinDLL('wtsapi32', use_last_error=True)


def _kernel32():
    return ctypes.WinDLL('kernel32', use_last_error=True)


def is_enabled() -> bool:
    enabled = wintypes.BOOL()
    return bool(_wts().WTSIsChildSessionsEnabled(ctypes.byref(enabled)) and enabled.value)


def enable(enabled: bool = True) -> bool:
    """Turn child sessions on or off for this computer. Needs admin."""
    return bool(_wts().WTSEnableChildSessions(bool(enabled)))


def current_session_id() -> int:
    session = wintypes.DWORD()
    kernel32 = _kernel32()
    kernel32.ProcessIdToSessionId(kernel32.GetCurrentProcessId(), ctypes.byref(session))
    return session.value


def process_session_id(pid: int):
    session = wintypes.DWORD()
    if _kernel32().ProcessIdToSessionId(pid, ctypes.byref(session)):
        return session.value
    return None


def child_session_id():
    """The child session of the calling (parent) session, or None.

    Only meaningful from the parent session; inside a child session it reports none.
    """
    session = wintypes.ULONG()
    if _wts().WTSGetChildSessionId(ctypes.byref(session)) and session.value != NO_SESSION:
        return session.value
    return None


def _session_info(session: int, info_class: int):
    wts = _wts()
    buf = ctypes.c_void_p()
    size = wintypes.DWORD()
    if not wts.WTSQuerySessionInformationW(None, session, info_class, ctypes.byref(buf), ctypes.byref(size)):
        return None
    try:
        return ctypes.string_at(buf, size.value)
    finally:
        wts.WTSFreeMemory(buf)


def session_state(session: int):
    raw = _session_info(session, _WTS_CONNECT_STATE)
    if not raw or len(raw) < 4:
        return None
    value = int.from_bytes(raw[:4], 'little')
    return _STATES[value] if value < len(_STATES) else str(value)


def in_child_session():
    """``(is_child, reason)`` for the calling process.

    ``WTSGetChildSessionId`` only works from the parent session, so inside a session
    check: not the console session, a remote session, and the client is this computer.
    """
    current = current_session_id()
    if current == _kernel32().WTSGetActiveConsoleSessionId():
        return False, 'console session'
    remote = _session_info(current, _WTS_IS_REMOTE_SESSION)
    client = _session_info(current, _WTS_CLIENT_NAME)
    client_name = client.decode('utf-16-le').rstrip('\0') if client else ''
    is_remote = bool(remote and remote[0])
    same_computer = client_name.lower() == os.environ.get('COMPUTERNAME', '').lower()
    return is_remote and same_computer, f'remote={is_remote} client={client_name!r}'


def logoff(session: int, wait: bool = True) -> bool:
    """Sign out ``session``. The user's own child session needs no admin."""
    return bool(_wts().WTSLogoffSession(None, session, bool(wait)))


def is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class _USER_INFO_24(ctypes.Structure):
    _fields_ = [('internet_identity', wintypes.BOOL), ('flags', wintypes.DWORD),
                ('internet_provider_name', wintypes.LPWSTR), ('internet_principal_name', wintypes.LPWSTR),
                ('user_sid', ctypes.c_void_p)]


def sign_in_name() -> str:
    """The user name RDP accepts for the current user.

    A Microsoft-account user must sign in as ``MicrosoftAccount\\<email>``; the local
    name and the display name are rejected. Local accounts use ``COMPUTER\\user``.
    """
    user = os.environ.get('USERNAME', '')
    netapi = ctypes.WinDLL('netapi32')
    buf = ctypes.c_void_p()
    if netapi.NetUserGetInfo(None, user, 24, ctypes.byref(buf)) == 0 and buf:
        try:
            info = ctypes.cast(buf, ctypes.POINTER(_USER_INFO_24)).contents
            if info.internet_identity and info.internet_principal_name:
                return f'{info.internet_provider_name}{BS}{info.internet_principal_name}'
        finally:
            netapi.NetApiBufferFree(buf)
    return f"{os.environ.get('COMPUTERNAME', '.')}{BS}{user}"
