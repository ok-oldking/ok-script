"""Open or focus Windows Explorer folders without creating duplicate windows."""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

_SVSI_SELECT = 0x1
_SVSI_DESELECTOTHERS = 0x4
_SVSI_ENSUREVISIBLE = 0x8
_SVSI_FOCUSED = 0x10


def open_explorer_folder(folder):
    """Open *folder*, or focus its existing Explorer window when it is open."""
    folder_path = Path(folder).resolve()
    folder_path.mkdir(parents=True, exist_ok=True)
    return _open_or_focus(folder_path)


def reveal_in_explorer(path):
    """Open the parent folder of *path* and select it when possible."""
    item_path = Path(path).resolve()
    return _open_or_focus(item_path.parent, item_path.name, item_path)


def _open_or_focus(folder, item_name=None, item_path=None):
    if sys.platform != 'win32':
        logger.warning('Windows Explorer is only available on Windows')
        return False

    if _focus_existing_explorer_window(folder, item_name):
        return True

    if item_path is not None:
        subprocess.Popen(['explorer', f'/select,{item_path}'])
    else:
        subprocess.Popen(['explorer', str(folder)])
    return True


def _get_explorer_windows():
    try:
        from win32com.client import Dispatch

        return list(Dispatch('Shell.Application').Windows())
    except Exception as error:
        logger.warning(f'Could not enumerate Explorer windows: {error}')
        return []


def _focus_existing_explorer_window(folder, item_name):
    com_initialized = False
    try:
        import pythoncom

        pythoncom.CoInitialize()
        com_initialized = True
        folder_key = _path_key(folder)
        for window in _get_explorer_windows():
            if _path_key(_window_folder(window)) != folder_key:
                continue
            _activate_window(window)
            if item_name:
                _select_item(window, item_name)
            return True
    except Exception as error:
        logger.warning(f'Could not focus an existing Explorer window: {error}')
    finally:
        if com_initialized:
            pythoncom.CoUninitialize()
    return False


def _window_folder(window):
    try:
        return _file_url_to_path(window.LocationURL)
    except Exception:
        return None


def _file_url_to_path(location_url):
    if not location_url:
        return None
    parsed = urlparse(location_url)
    if parsed.scheme.lower() != 'file':
        return None

    path = unquote(parsed.path)
    if parsed.netloc:
        return '\\\\' + parsed.netloc + path.replace('/', '\\')
    if len(path) >= 3 and path[0] == '/' and path[2] == ':':
        path = path[1:]
    return path.replace('/', '\\')


def _path_key(path):
    if path is None:
        return None
    return os.path.normcase(os.path.normpath(os.path.abspath(os.fspath(path))))


def _activate_window(window):
    try:
        window.Visible = True
        window.WindowState = 1  # SW_SHOWNORMAL
    except Exception:
        pass

    try:
        import win32con
        import win32gui

        hwnd = int(window.HWND)
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
    except Exception as error:
        logger.warning(f'Could not activate Explorer window: {error}')


def _select_item(window, item_name):
    try:
        folder_item = window.Document.Folder.ParseName(item_name)
        if folder_item is not None:
            flags = _SVSI_SELECT | _SVSI_DESELECTOTHERS | _SVSI_ENSUREVISIBLE | _SVSI_FOCUSED
            window.Document.SelectItem(folder_item, flags)
    except Exception as error:
        logger.warning(f'Could not select Explorer item {item_name}: {error}')
