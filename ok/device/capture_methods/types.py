import sys
from enum import IntEnum

import win32gui

class ImageShape(IntEnum):
    Y = 0
    X = 1
    Channels = 2



class ColorChannel(IntEnum):
    Blue = 0
    Green = 1
    Red = 2
    Alpha = 3



def decimal(value: float):
    return f"{int(value * 100) / 100}".ljust(4, "0")



def is_digit(value: str | int | None):
    if value is None:
        return False
    try:
        return 0 <= int(value) <= 9
    except (ValueError, TypeError):
        return False



def is_valid_hwnd(hwnd: int):
    if not hwnd:
        return False
    if sys.platform == "win32":
        return bool(win32gui.IsWindow(hwnd) and win32gui.GetWindowText(hwnd))
    return True
