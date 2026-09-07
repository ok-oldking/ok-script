"""Platform-neutral and ADB key helpers.

The Win32 virtual-key table is loaded lazily from ``windows_keys`` so importing
ADB/common interaction code on another platform does not require PyWin32.
"""

from __future__ import annotations

import importlib

from ok.platform import WINDOWS, require_platform


PYDIRECT_KEY_MAP = {
    'alt_l': 'altleft',
    'alt_r': 'altright',
    'lalt': 'altleft',
    'ralt': 'altright',
    'ctrl_l': 'ctrlleft',
    'ctrl_r': 'ctrlright',
    'lctrl': 'ctrlleft',
    'rctrl': 'ctrlright',
    'lcontrol': 'ctrlleft',
    'rcontrol': 'ctrlright',
    'shift_l': 'shiftleft',
    'shift_r': 'shiftright',
    'lshift': 'shiftleft',
    'rshift': 'shiftright',
    'page_up': 'pageup',
    'page_down': 'pagedown',
    'caps_lock': 'capslock',
    'num_lock': 'numlock',
    'scroll_lock': 'scrolllock',
    'print_screen': 'printscreen',
    'cmd': 'win',
    'cmd_l': 'win',
    'cmd_r': 'win',
    'command': 'win',
    'meta': 'win',
    'windows': 'win',
}


def normalize_pydirect_key(key):
    key = str(key)
    return PYDIRECT_KEY_MAP.get(key.lower(), key)


ADB_KEY_MAP = {
    'esc': 'KEYCODE_ESCAPE',
    'enter': 'KEYCODE_ENTER',
    'return': 'KEYCODE_ENTER',
    'space': 'KEYCODE_SPACE',
    'backspace': 'KEYCODE_DEL',
    'delete': 'KEYCODE_FORWARD_DEL',
    'tab': 'KEYCODE_TAB',
    'home': 'KEYCODE_HOME',
    'pageup': 'KEYCODE_PAGE_UP',
    'page_up': 'KEYCODE_PAGE_UP',
    'pagedown': 'KEYCODE_PAGE_DOWN',
    'page_down': 'KEYCODE_PAGE_DOWN',
    'up': 'KEYCODE_DPAD_UP',
    'down': 'KEYCODE_DPAD_DOWN',
    'left': 'KEYCODE_DPAD_LEFT',
    'right': 'KEYCODE_DPAD_RIGHT',
    'alt': 'KEYCODE_ALT_LEFT',
    'lalt': 'KEYCODE_ALT_LEFT',
    'alt_l': 'KEYCODE_ALT_LEFT',
    'ralt': 'KEYCODE_ALT_RIGHT',
    'alt_r': 'KEYCODE_ALT_RIGHT',
    'alt_gr': 'KEYCODE_ALT_RIGHT',
    'ctrl': 'KEYCODE_CTRL_LEFT',
    'control': 'KEYCODE_CTRL_LEFT',
    'lctrl': 'KEYCODE_CTRL_LEFT',
    'lcontrol': 'KEYCODE_CTRL_LEFT',
    'ctrl_l': 'KEYCODE_CTRL_LEFT',
    'rctrl': 'KEYCODE_CTRL_RIGHT',
    'rcontrol': 'KEYCODE_CTRL_RIGHT',
    'ctrl_r': 'KEYCODE_CTRL_RIGHT',
    'shift': 'KEYCODE_SHIFT_LEFT',
    'lshift': 'KEYCODE_SHIFT_LEFT',
    'shift_l': 'KEYCODE_SHIFT_LEFT',
    'rshift': 'KEYCODE_SHIFT_RIGHT',
    'shift_r': 'KEYCODE_SHIFT_RIGHT',
    'capslock': 'KEYCODE_CAPS_LOCK',
    'caps_lock': 'KEYCODE_CAPS_LOCK',
    'numlock': 'KEYCODE_NUM_LOCK',
    'num_lock': 'KEYCODE_NUM_LOCK',
    'scrolllock': 'KEYCODE_SCROLL_LOCK',
    'scroll_lock': 'KEYCODE_SCROLL_LOCK',
    'printscreen': 'KEYCODE_SYSRQ',
    'print_screen': 'KEYCODE_SYSRQ',
}


__all__ = [
    'ADB_KEY_MAP',
    'PYDIRECT_KEY_MAP',
    'normalize_pydirect_key',
    'vk_key_dict',
]


def __getattr__(name):
    if name != 'vk_key_dict':
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    require_platform('Win32 virtual-key map', (WINDOWS,))
    value = importlib.import_module(
        'ok.device.interaction_methods.windows_keys').vk_key_dict
    globals()[name] = value
    return value
