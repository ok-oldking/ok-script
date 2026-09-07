"""Capture backend exports with platform-safe lazy loading.

Shared capture contracts remain importable everywhere. Windows-specific
implementations are imported only when explicitly requested on Windows.
"""

from __future__ import annotations

import importlib
import sys

from ok.device.capture_methods.adb import ADBCaptureMethod
from ok.device.capture_methods.base import BaseCaptureMethod, BaseWindowsCaptureMethod
from ok.device.capture_methods.nemu_ipc import NemuIpcCaptureMethod
from ok.device.capture_methods.types import ColorChannel, ImageShape, decimal, is_digit, is_valid_hwnd
from ok.platform import MACOS, WINDOWS, require_platform


_COMMON_EXPORTS = [
    'ADBCaptureMethod',
    'BaseCaptureMethod',
    'BaseWindowsCaptureMethod',
    'ColorChannel',
    'ImageShape',
    'NemuIpcCaptureMethod',
    'decimal',
    'is_digit',
    'is_valid_hwnd',
]

_LAZY_EXPORTS = {
    'ImageCaptureMethod': ('ok.device.capture_methods.image', 'ImageCaptureMethod'),
}

_MACOS_EXPORTS = {
    'ScreenCaptureKitCaptureMethod': (
        'ok.device.capture_methods.screencapturekit',
        'ScreenCaptureKitCaptureMethod',
    ),
}

_WINDOWS_EXPORTS = {
    'BitBltCaptureMethod': ('ok.device.capture_methods.bitblt', 'BitBltCaptureMethod'),
    'ForegroundBitBltCaptureMethod': ('ok.device.capture_methods.bitblt', 'ForegroundBitBltCaptureMethod'),
    'BGRA_CHANNEL_COUNT': ('ok.device.capture_methods.bitblt_utils', 'BGRA_CHANNEL_COUNT'),
    'PBYTE': ('ok.device.capture_methods.bitblt_utils', 'PBYTE'),
    'PW_CLIENT_ONLY': ('ok.device.capture_methods.bitblt_utils', 'PW_CLIENT_ONLY'),
    'PW_RENDERFULLCONTENT': ('ok.device.capture_methods.bitblt_utils', 'PW_RENDERFULLCONTENT'),
    'BitBltCtxDummy': ('ok.device.capture_methods.bitblt_utils', 'BitBltCtxDummy'),
    'capture_by_bitblt': ('ok.device.capture_methods.bitblt_utils', 'capture_by_bitblt'),
    'capture_desktop_by_bitblt': ('ok.device.capture_methods.bitblt_utils', 'capture_desktop_by_bitblt'),
    'clean_up_bitblt': ('ok.device.capture_methods.bitblt_utils', 'clean_up_bitblt'),
    'clean_up_desktop_bitblt': ('ok.device.capture_methods.bitblt_utils', 'clean_up_desktop_bitblt'),
    'composite_hwnds': ('ok.device.capture_methods.bitblt_utils', 'composite_hwnds'),
    'get_crop_point': ('ok.device.capture_methods.bitblt_utils', 'get_crop_point'),
    'parse_reg_flag': ('ok.device.capture_methods.bitblt_utils', 'parse_reg_flag'),
    'try_delete_dc': ('ok.device.capture_methods.bitblt_utils', 'try_delete_dc'),
    'BrowserCaptureMethod': ('ok.device.capture_methods.browser', 'BrowserCaptureMethod'),
    'BrowserWGC': ('ok.device.capture_methods.browser', 'BrowserWGC'),
    'BrowserWindowAdapter': ('ok.device.capture_methods.browser', 'BrowserWindowAdapter'),
    'DesktopDuplicationCaptureMethod': (
        'ok.device.capture_methods.desktop_duplication', 'DesktopDuplicationCaptureMethod'),
    'HwndWindow': ('ok.device.capture_methods.hwnd_window', 'HwndWindow'),
    'check_pos': ('ok.device.capture_methods.hwnd_window', 'check_pos'),
    'get_monitors_bounds': ('ok.device.capture_methods.hwnd_window', 'get_monitors_bounds'),
    'get_mute_state': ('ok.device.capture_methods.hwnd_window', 'get_mute_state'),
    'is_window_in_screen_bounds': (
        'ok.device.capture_methods.hwnd_window', 'is_window_in_screen_bounds'),
    'set_mute_state': ('ok.device.capture_methods.hwnd_window', 'set_mute_state'),
    'get_capture': ('ok.device.capture_methods.update', 'get_capture'),
    'get_win_graphics_capture': (
        'ok.device.capture_methods.update', 'get_win_graphics_capture'),
    'update_capture_method': ('ok.device.capture_methods.update', 'update_capture_method'),
    'WindowsGraphicsCaptureMethod': (
        'ok.device.capture_methods.windows_graphics', 'WindowsGraphicsCaptureMethod'),
}

__all__ = [*_COMMON_EXPORTS, *_LAZY_EXPORTS]
if sys.platform == WINDOWS:
    __all__.extend(_WINDOWS_EXPORTS)
elif sys.platform == MACOS:
    __all__.extend(_MACOS_EXPORTS)


def __getattr__(name):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        target = _MACOS_EXPORTS.get(name)
        if target is not None:
            require_platform(f'macOS capture export {name}', (MACOS,))
    if target is None:
        target = _WINDOWS_EXPORTS.get(name)
        if target is None:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        require_platform(f'Windows capture export {name}', (WINDOWS,))
    module_name, attribute_name = target
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
