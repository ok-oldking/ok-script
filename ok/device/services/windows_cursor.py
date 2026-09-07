"""Win32 cursor service implementation."""

from __future__ import annotations

import win32api


class WindowsCursorService:
    @property
    def available(self) -> bool:
        return True

    def get_position(self) -> tuple[int, int]:
        x, y = win32api.GetCursorPos()
        return int(x), int(y)

    def set_position(self, position: tuple[int, int]) -> None:
        x, y = position
        win32api.SetCursorPos((int(x), int(y)))
