"""Logical OK task keys mapped to public macOS virtual key codes."""

from __future__ import annotations


# Values are the public kVK_* constants declared by HIToolbox/Events.h.  Keep
# this table independent from Quartz imports so shared key validation remains
# importable on every platform.
MACOS_KEY_MAP = {
    "a": 0x00,
    "s": 0x01,
    "d": 0x02,
    "f": 0x03,
    "h": 0x04,
    "g": 0x05,
    "z": 0x06,
    "x": 0x07,
    "c": 0x08,
    "v": 0x09,
    "b": 0x0B,
    "q": 0x0C,
    "w": 0x0D,
    "e": 0x0E,
    "r": 0x0F,
    "y": 0x10,
    "t": 0x11,
    "1": 0x12,
    "2": 0x13,
    "3": 0x14,
    "4": 0x15,
    "6": 0x16,
    "5": 0x17,
    "=": 0x18,
    "9": 0x19,
    "7": 0x1A,
    "-": 0x1B,
    "8": 0x1C,
    "0": 0x1D,
    "]": 0x1E,
    "o": 0x1F,
    "u": 0x20,
    "[": 0x21,
    "i": 0x22,
    "p": 0x23,
    "enter": 0x24,
    "return": 0x24,
    "l": 0x25,
    "j": 0x26,
    "'": 0x27,
    "k": 0x28,
    ";": 0x29,
    "\\": 0x2A,
    ",": 0x2B,
    "/": 0x2C,
    "n": 0x2D,
    "m": 0x2E,
    ".": 0x2F,
    "tab": 0x30,
    "space": 0x31,
    "`": 0x32,
    "backspace": 0x33,
    "esc": 0x35,
    "escape": 0x35,
    "command": 0x37,
    "cmd": 0x37,
    "lshift": 0x38,
    "shift": 0x38,
    "capslock": 0x39,
    "lalt": 0x3A,
    "alt": 0x3A,
    "lctrl": 0x3B,
    "control": 0x3B,
    "ctrl": 0x3B,
    "rshift": 0x3C,
    "ralt": 0x3D,
    "rctrl": 0x3E,
    "f17": 0x40,
    "f18": 0x4F,
    "f19": 0x50,
    "f20": 0x5A,
    "f5": 0x60,
    "f6": 0x61,
    "f7": 0x62,
    "f3": 0x63,
    "f8": 0x64,
    "f9": 0x65,
    "f11": 0x67,
    "f13": 0x69,
    "f16": 0x6A,
    "f14": 0x6B,
    "f10": 0x6D,
    "f12": 0x6F,
    "f15": 0x71,
    "help": 0x72,
    "home": 0x73,
    "pageup": 0x74,
    "page_up": 0x74,
    "delete": 0x75,
    "forward_delete": 0x75,
    "f4": 0x76,
    "end": 0x77,
    "f2": 0x78,
    "pagedown": 0x79,
    "page_down": 0x79,
    "f1": 0x7A,
    "left": 0x7B,
    "right": 0x7C,
    "down": 0x7D,
    "up": 0x7E,
}


def macos_key_code(key: object) -> int:
    """Return one CGKeyCode and reject unknown logical task keys."""
    if isinstance(key, bool):
        raise ValueError(f"unsupported macOS key: {key!r}")
    if isinstance(key, int) and 0 <= key <= 0xFFFF:
        return key
    normalized = str(key).strip().lower()
    try:
        return MACOS_KEY_MAP[normalized]
    except KeyError as error:
        raise ValueError(f"unsupported macOS key: {key!r}") from error


__all__ = ["MACOS_KEY_MAP", "macos_key_code"]
