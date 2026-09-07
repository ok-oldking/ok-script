"""Platform-selected game overlay implementations."""

from __future__ import annotations

import importlib
import sys

from ok.platform import WINDOWS, require_platform


__all__ = ['Win32GdiOverlay'] if sys.platform == WINDOWS else []


def __getattr__(name):
    if name != 'Win32GdiOverlay':
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    require_platform('Win32 GDI overlay', (WINDOWS,))
    value = importlib.import_module('ok.ui.overlay.win32_gdi').Win32GdiOverlay
    globals()[name] = value
    return value
