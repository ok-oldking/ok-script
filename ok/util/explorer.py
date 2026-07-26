"""Open or focus Windows Explorer folders without creating duplicate windows."""

import ctypes
import os
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
    logger.info(f'open folder requested: input={os.fspath(folder)!r}, cwd={os.getcwd()!r}')
    folder_path = Path(folder).resolve()
    logger.info(
        f'open folder resolved: path={str(folder_path)!r}, '
        f'exists={folder_path.exists()}, is_dir={folder_path.is_dir()}'
    )
    folder_path.mkdir(parents=True, exist_ok=True)
    logger.info(f'open folder ready: path={str(folder_path)!r}, exists={folder_path.exists()}')
    return _open_or_focus(folder_path)


def reveal_in_explorer(path):
    """Open the parent folder of *path* and select it when possible."""
    item_path = Path(path).resolve()
    return _open_or_focus(item_path.parent, item_path.name, item_path)


def _open_or_focus(folder, item_name=None, item_path=None):
    logger.info(
        f'Explorer dispatch: folder={str(folder)!r}, item_name={item_name!r}, '
        f'item_path={str(item_path) if item_path is not None else None!r}, '
        f'platform={sys.platform!r}'
    )
    if sys.platform != 'win32':
        logger.warning('Windows Explorer is only available on Windows')
        return False

    if _focus_existing_explorer_window(folder, item_name):
        logger.info(f'Explorer focused existing window: folder={str(folder)!r}')
        return True

    if item_path is not None:
        logger.info(f'Explorer launching native selection: item={str(item_path)!r}')
        if not _open_and_select_item(item_path):
            logger.warning(
                f'Native Explorer selection failed; opening parent folder: '
                f'folder={str(folder)!r}'
            )
            os.startfile(str(folder), 'explore')
    else:
        # Use the shell's directory verb instead of Explorer's command-line
        # parser.  The latter can fall back to a known parent folder (notably
        # OneDrive Documents) instead of navigating to the requested child.
        logger.info(f'Explorer launching directory: path={str(folder)!r}, verb="explore"')
        os.startfile(str(folder), 'explore')
    logger.info('Explorer launch request completed')
    return True


def _open_and_select_item(item_path):
    """Open an item's parent and select it using the Windows Shell API."""
    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    shell32.SHParseDisplayName.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    shell32.SHParseDisplayName.restype = ctypes.c_long
    shell32.SHOpenFolderAndSelectItems.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_ulong,
    ]
    shell32.SHOpenFolderAndSelectItems.restype = ctypes.c_long
    ole32.CoInitialize.argtypes = [ctypes.c_void_p]
    ole32.CoInitialize.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None

    pidl = ctypes.c_void_p()
    attributes = ctypes.c_ulong()
    com_result = ole32.CoInitialize(None)
    should_uninitialize = com_result in (0, 1)  # S_OK or S_FALSE

    try:
        parse_result = shell32.SHParseDisplayName(
            str(item_path), None, ctypes.byref(pidl), 0, ctypes.byref(attributes)
        )
        logger.info(
            f'SHParseDisplayName result: item={str(item_path)!r}, '
            f'hresult={_format_hresult(parse_result)}, pidl={bool(pidl.value)}'
        )
        if parse_result < 0 or not pidl.value:
            return False

        select_result = shell32.SHOpenFolderAndSelectItems(pidl, 0, None, 0)
        logger.info(
            f'SHOpenFolderAndSelectItems result: item={str(item_path)!r}, '
            f'hresult={_format_hresult(select_result)}'
        )
        return select_result >= 0
    except Exception as error:
        logger.error(f'Native Explorer selection failed for {str(item_path)!r}', error)
        return False
    finally:
        if pidl.value:
            ole32.CoTaskMemFree(pidl)
        if should_uninitialize:
            ole32.CoUninitialize()


def _format_hresult(result):
    return f'0x{result & 0xFFFFFFFF:08X}'


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
        windows = _get_explorer_windows()
        logger.info(
            f'Explorer existing-window scan: target={str(folder)!r}, '
            f'target_key={folder_key!r}, windows={len(windows)}'
        )
        for index, window in enumerate(windows):
            window_folder = _window_folder(window)
            window_key = _path_key(window_folder)
            logger.info(
                f'Explorer window candidate: index={index}, '
                f'folder={window_folder!r}, key={window_key!r}, '
                f'matches={window_key == folder_key}'
            )
            if window_key != folder_key:
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
