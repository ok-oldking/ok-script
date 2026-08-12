"""Native Windows tray notifications for runtimes without a Qt event loop."""

from __future__ import annotations

import os
import re
import tempfile
import threading
import ctypes
from ctypes import wintypes

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8),
    ]


class _NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD), ("guidItem", _GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


def _show_balloon(hwnd, icon, title, message):
    if os.name != "nt":
        return False
    data = _NOTIFYICONDATAW()
    data.cbSize = ctypes.sizeof(data)
    data.hWnd = int(hwnd)
    data.uID = 1
    data.uFlags = 0x10  # NIF_INFO
    data.szInfo = str(message)[:255]
    data.szInfoTitle = str(title)[:63]
    data.dwInfoFlags = 0x4  # NIIF_USER: use hBalloonIcon, not Python's generic glyph
    data.hBalloonIcon = int(icon)
    return bool(ctypes.windll.shell32.Shell_NotifyIconW(0x1, ctypes.byref(data)))  # NIM_MODIFY


def _add_tray_icon(hwnd, icon, tooltip, callback_message):
    """Register the headless notification icon without PyWin32 tuple marshalling."""
    if os.name != "nt":
        return False
    data = _NOTIFYICONDATAW()
    data.cbSize = ctypes.sizeof(data)
    data.hWnd = int(hwnd)
    data.uID = 1
    data.uFlags = 0x1 | 0x2 | 0x4  # NIF_MESSAGE | NIF_ICON | NIF_TIP
    data.uCallbackMessage = int(callback_message)
    data.hIcon = int(icon)
    data.szTip = str(tooltip)[:127]
    return bool(ctypes.windll.shell32.Shell_NotifyIconW(0x0, ctypes.byref(data)))  # NIM_ADD


def _delete_tray_icon(hwnd):
    if os.name != "nt":
        return False
    data = _NOTIFYICONDATAW()
    data.cbSize = ctypes.sizeof(data)
    data.hWnd = int(hwnd)
    data.uID = 1
    return bool(ctypes.windll.shell32.Shell_NotifyIconW(0x2, ctypes.byref(data)))  # NIM_DELETE


class WindowsSystemNotifier:
    """Own a hidden Win32 window and notification-area icon."""

    def __init__(self, app_name="ok-script", app_icon=None):
        self.app_name = str(app_name or "ok-script")
        self.app_icon = self._resolve_icon(app_icon)
        self.app_id = "ok-script." + re.sub(r"[^A-Za-z0-9._-]+", ".", self.app_name).strip(".")
        self._ready = threading.Event()
        self._closed = False
        self._hwnd = 0
        self._hicon = 0
        self._registered = False
        self._thread = None
        if os.name == "nt":
            self._thread = threading.Thread(
                target=self._run, name="WindowsSystemNotifier", daemon=True)
            self._thread.start()
            self._ready.wait(2)

    def show(self, title, message, error=False):
        if not getattr(self, '_registered', True) or not self._hwnd or self._closed:
            return False
        try:
            display_title = str(title or self.app_name)
            if error and title:
                display_title = str(title)
            return _show_balloon(
                self._hwnd, self._hicon, display_title, str(message))
        except Exception as exception:
            logger.error("Windows system notification failed", exception)
            return False

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._hwnd:
            try:
                import win32con
                import win32gui
                if self._registered:
                    _delete_tray_icon(self._hwnd)
                    self._registered = False
                win32gui.PostMessage(self._hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception as exception:
                logger.debug(f"Windows system notifier cleanup failed: {exception}")
        if self._thread and self._thread != threading.current_thread():
            self._thread.join(timeout=1)

    def _run(self):
        try:
            import ctypes
            import win32api
            import win32con
            import win32gui

            instance = win32api.GetModuleHandle(None)
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(self.app_id)
            except (AttributeError, OSError):
                pass
            class_name = f"ok-script.SystemNotifier.{id(self)}"

            def on_destroy(_hwnd, _message, _wparam, _lparam):
                win32gui.PostQuitMessage(0)
                return 0

            window_class = win32gui.WNDCLASS()
            window_class.hInstance = instance
            window_class.lpszClassName = class_name
            window_class.hIcon = self._load_icon(win32gui, win32con)
            window_class.lpfnWndProc = {win32con.WM_DESTROY: on_destroy}
            win32gui.RegisterClass(window_class)
            self._hwnd = win32gui.CreateWindow(
                class_name, self.app_name,
                win32con.WS_OVERLAPPED | win32con.WS_SYSMENU,
                0, 0, 0, 0,
                0, 0, instance, None)
            self._hicon = window_class.hIcon
            self._registered = _add_tray_icon(
                self._hwnd, self._hicon, self.app_name, win32con.WM_USER + 20)
            if not self._registered:
                raise RuntimeError("Shell_NotifyIconW(NIM_ADD) rejected the headless tray icon")
        except Exception as exception:
            logger.error("Windows system notifier startup failed", exception)
        finally:
            self._ready.set()
        if self._hwnd:
            win32gui.PumpMessages()

    def _load_icon(self, win32gui, win32con):
        icon_path = self.app_icon
        temporary_icon = None
        if icon_path and os.path.isfile(icon_path) and not icon_path.lower().endswith(".ico"):
            try:
                from PIL import Image
                handle, temporary_icon = tempfile.mkstemp(suffix=".ico")
                os.close(handle)
                with Image.open(icon_path) as image:
                    image.convert("RGBA").save(
                        temporary_icon, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
                icon_path = temporary_icon
            except (ImportError, OSError, ValueError) as exception:
                logger.debug(f"Failed to convert system notification icon: {exception}")
        if icon_path and os.path.isfile(icon_path):
            try:
                return win32gui.LoadImage(
                    0, icon_path, win32con.IMAGE_ICON, 0, 0,
                    win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE)
            except Exception as exception:
                logger.debug(f"Failed to load system notification icon: {exception}")
            finally:
                if temporary_icon:
                    try:
                        os.remove(temporary_icon)
                    except OSError:
                        pass
        return win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

    @staticmethod
    def _resolve_icon(app_icon):
        if not app_icon or str(app_icon).startswith(":/"):
            return ""
        from ok.util.file import get_path_relative_to_exe
        return str(get_path_relative_to_exe(str(app_icon)) or "")


class TraySystemNotifier:
    """Adapt an existing UI tray icon to the shared notification manager."""

    def __init__(self, tray, information_icon, error_icon):
        self.tray = tray
        self.information_icon = information_icon
        self.error_icon = error_icon

    def show(self, title, message, error=False):
        self.tray.showMessage(
            title, message, self.error_icon if error else self.information_icon, 5000)
        return True

    def close(self):
        pass
