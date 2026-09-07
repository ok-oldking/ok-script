"""Platform-neutral cursor service selection.

The default factory remains target-independent. DeviceManager replaces it with
the guarded Quartz cursor service only after a macOS target/input backend exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ok.platform import MACOS, WINDOWS, PlatformUnavailableError


@runtime_checkable
class CursorService(Protocol):
    """Query and move the system cursor through a platform implementation."""

    @property
    def available(self) -> bool: ...

    def get_position(self) -> tuple[int, int]: ...

    def set_position(self, position: tuple[int, int]) -> None: ...


@dataclass(frozen=True)
class UnavailableCursorService:
    platform_name: str
    reason: str

    @property
    def available(self) -> bool:
        return False

    def _raise(self) -> None:
        raise PlatformUnavailableError(
            f'Cursor service is unavailable on platform {self.platform_name!r}: '
            f'{self.reason}')

    def get_position(self) -> tuple[int, int]:
        self._raise()

    def set_position(self, position: tuple[int, int]) -> None:
        del position
        self._raise()


def create_cursor_service(platform_name: str | None = None) -> CursorService:
    """Return the current platform service without importing other backends."""
    if platform_name is None:
        import sys
        platform_name = sys.platform

    if platform_name == WINDOWS:
        from ok.device.services.windows_cursor import WindowsCursorService
        return WindowsCursorService()
    if platform_name == MACOS:
        return UnavailableCursorService(
            platform_name,
            'a bound Quartz foreground interaction is required',
        )
    return UnavailableCursorService(
        platform_name,
        'no cursor backend is registered for this platform',
    )
