"""Compatibility facade for the framework-independent Win32 overlay."""

from __future__ import annotations

import importlib
import sys

from ok.platform import WINDOWS, require_platform


__all__ = ['GdiCanvas', 'OverlayWindow', 'Win32GdiOverlay'] if sys.platform == WINDOWS else []


def __getattr__(name):
    if name not in {'GdiCanvas', 'OverlayWindow', 'Win32GdiOverlay'}:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    require_platform('Win32 GDI overlay', (WINDOWS,))
    module = importlib.import_module('ok.ui.overlay.win32_gdi')
    attribute_name = 'Win32GdiOverlay' if name == 'OverlayWindow' else name
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value
