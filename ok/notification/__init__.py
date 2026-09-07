"""Notification providers with platform-safe exports."""

from __future__ import annotations

import importlib
import sys

from ok.notification.manager import NotificationManager
from ok.notification.system import TraySystemNotifier
from ok.platform import WINDOWS, require_platform


__all__ = ['NotificationManager', 'TraySystemNotifier']
if sys.platform == WINDOWS:
    __all__.append('WindowsSystemNotifier')


def __getattr__(name):
    if name != 'WindowsSystemNotifier':
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    require_platform('Windows system notifier', (WINDOWS,))
    value = importlib.import_module(
        'ok.notification.system').WindowsSystemNotifier
    globals()[name] = value
    return value
