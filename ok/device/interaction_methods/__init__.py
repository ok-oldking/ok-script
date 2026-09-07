"""Interaction backend exports with platform-safe lazy loading."""

from __future__ import annotations

import importlib
import sys

from ok.device.interaction_methods.adb import ADBInteraction
from ok.device.interaction_methods.base import BaseInteraction
from ok.device.interaction_methods.browser import BrowserInteraction
from ok.device.interaction_methods.do_nothing import DoNothingInteraction
from ok.device.interaction_methods.keys import (
    ADB_KEY_MAP,
    PYDIRECT_KEY_MAP,
    normalize_pydirect_key,
)
from ok.device.interaction_methods.swipe import insert_swipe
from ok.platform import MACOS, WINDOWS, require_platform


_COMMON_EXPORTS = [
    'ADBInteraction',
    'ADB_KEY_MAP',
    'BaseInteraction',
    'BrowserInteraction',
    'DoNothingInteraction',
    'PYDIRECT_KEY_MAP',
    'insert_swipe',
    'normalize_pydirect_key',
]

_WINDOWS_EXPORTS = {
    'ForegroundPostMessageInteraction': (
        'ok.device.interaction_methods.foreground_post_message',
        'ForegroundPostMessageInteraction'),
    'GenshinInteraction': ('ok.device.interaction_methods.genshin', 'GenshinInteraction'),
    'INPUT': ('ok.device.interaction_methods.genshin', 'INPUT'),
    'MOUSEINPUT': ('ok.device.interaction_methods.genshin', 'MOUSEINPUT'),
    'SendInput': ('ok.device.interaction_methods.genshin', 'SendInput'),
    'PostMessageInteraction': (
        'ok.device.interaction_methods.post_message', 'PostMessageInteraction'),
    'PyDirectInteraction': ('ok.device.interaction_methods.pydirect', 'PyDirectInteraction'),
    'PynputInteraction': ('ok.device.interaction_methods.pynput', 'PynputInteraction'),
    'vk_key_dict': ('ok.device.interaction_methods.windows_keys', 'vk_key_dict'),
}

_MACOS_EXPORTS = {
    'QuartzForegroundInteraction': (
        'ok.device.interaction_methods.quartz', 'QuartzForegroundInteraction'),
}

__all__ = list(_COMMON_EXPORTS)
if sys.platform == WINDOWS:
    __all__.extend(_WINDOWS_EXPORTS)
elif sys.platform == MACOS:
    __all__.extend(_MACOS_EXPORTS)


def __getattr__(name):
    target = _WINDOWS_EXPORTS.get(name)
    platform = WINDOWS
    platform_label = 'Windows'
    if target is None:
        target = _MACOS_EXPORTS.get(name)
        platform = MACOS
        platform_label = 'macOS'
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    require_platform(f'{platform_label} interaction export {name}', (platform,))
    module_name, attribute_name = target
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
