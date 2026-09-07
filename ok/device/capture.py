"""Compatibility facade for the historical ``ok.device.capture`` module.

Exports are delegated lazily so importing shared capture contracts does not
load Win32 capture implementations on other platforms.
"""

from __future__ import annotations

import importlib
import sys

from ok.device import capture_methods as _capture_methods
from ok.platform import WINDOWS, require_platform


__all__ = list(_capture_methods.__all__)
if sys.platform == WINDOWS:
    __all__.append('render_full')


def __getattr__(name):
    if name == 'render_full':
        require_platform('BitBlt render mode', (WINDOWS,))
        value = importlib.import_module(
            'ok.device.capture_methods.bitblt').render_full
    else:
        value = getattr(_capture_methods, name)
    globals()[name] = value
    return value
