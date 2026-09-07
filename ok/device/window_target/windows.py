"""Windows adapter for the existing :class:`HwndWindow` implementation.

This module uses composition and leaves the legacy capture/interaction object
unchanged.  Win32 is imported lazily only when the default PID resolver runs.
"""

from __future__ import annotations

from pathlib import PureWindowsPath
import time
from typing import Callable

from ok.device.window_target.base import (
    BaseDesktopWindowTarget,
    WindowCandidate,
    WindowCoordinateSpace,
    WindowGeometry,
    WindowRefreshResult,
    WindowRefreshStatus,
)


def _default_process_id(hwnd: int) -> int:
    import win32process
    return int(win32process.GetWindowThreadProcessId(hwnd)[1])


class WindowsHwndWindowTarget(BaseDesktopWindowTarget):
    """Expose an existing ``HwndWindow`` through the neutral target contract."""

    def __init__(
            self,
            hwnd_window,
            *,
            process_id_resolver: Callable[[int], int] | None = None,
            monotonic: Callable[[], float] = time.monotonic,
            sleep: Callable[[float], None] = time.sleep):
        self.hwnd_window = hwnd_window
        self._process_id_resolver = process_id_resolver or _default_process_id
        self._monotonic = monotonic
        self._sleep = sleep
        super().__init__(self._read_candidate())

    def _read_candidate(self) -> WindowCandidate | None:
        hwnd = int(getattr(self.hwnd_window, "hwnd", 0) or 0)
        if not hwnd or not bool(getattr(self.hwnd_window, "exists", False)):
            return None

        process_id = self._process_id_resolver(hwnd)
        x = float(getattr(self.hwnd_window, "x", 0))
        y = float(getattr(self.hwnd_window, "y", 0))
        window_width = float(
            getattr(self.hwnd_window, "window_width", 0)
            or getattr(self.hwnd_window, "width", 0)
        )
        window_height = float(
            getattr(self.hwnd_window, "window_height", 0)
            or getattr(self.hwnd_window, "height", 0)
        )
        content_width = float(getattr(self.hwnd_window, "width", 0))
        content_height = float(getattr(self.hwnd_window, "height", 0))
        capture_x, capture_y = self.hwnd_window.get_capture_origin()
        capture_width = float(
            getattr(self.hwnd_window, "real_width", 0) or content_width)
        capture_height = float(
            getattr(self.hwnd_window, "real_height", 0) or content_height)
        executable = str(getattr(self.hwnd_window, "exe_full_path", "") or "")
        title = str(getattr(self.hwnd_window, "hwnd_title", "") or "")

        return WindowCandidate(
            process_id=process_id,
            window_id=hwnd,
            bundle_identifier=None,
            application_name=PureWindowsPath(executable).name if executable else "",
            title=title,
            layer=0,
            outer_geometry=WindowGeometry(
                x, y, window_width, window_height,
                WindowCoordinateSpace.WINDOWS_LEGACY_DESKTOP),
            content_geometry=WindowGeometry(
                x, y, content_width, content_height,
                WindowCoordinateSpace.WINDOWS_LEGACY_DESKTOP),
            capture_geometry=WindowGeometry(
                float(capture_x), float(capture_y), capture_width, capture_height,
                WindowCoordinateSpace.WINDOWS_LEGACY_CAPTURE),
            display_scale=float(getattr(self.hwnd_window, "scaling", 1.0) or 1.0),
            frontmost=bool(self.hwnd_window.is_foreground()),
        )

    def refresh(self) -> WindowRefreshResult:
        previous = self.snapshot
        previous_identity = (
            previous.candidate.runtime_identity if previous.candidate else None)
        self.hwnd_window.do_update_window_size()
        candidate = self._read_candidate()
        changed = self._update_candidate(candidate, exists=candidate is not None)
        current_identity = candidate.runtime_identity if candidate else None

        if candidate is None:
            status = WindowRefreshStatus.LOST
        elif (
                not previous.exists
                or (previous_identity is not None
                    and previous_identity != current_identity)):
            status = WindowRefreshStatus.REBOUND
        elif changed:
            status = WindowRefreshStatus.UPDATED
        else:
            status = WindowRefreshStatus.UNCHANGED
        return WindowRefreshResult(status, previous, self.snapshot)

    def exists(self) -> bool:
        return bool(
            self.snapshot.exists
            and getattr(self.hwnd_window, "exists", False)
            and getattr(self.hwnd_window, "hwnd", 0)
        )

    def is_foreground(self) -> bool:
        return self.exists() and bool(self.hwnd_window.is_foreground())

    def request_activation(self) -> bool:
        return self.exists() and bool(self.hwnd_window.bring_to_front())

    def wait_for_observed_activation(
            self, timeout: float, poll_interval: float = 0.05) -> bool:
        if timeout < 0 or poll_interval <= 0:
            raise ValueError("timeout must be non-negative and poll_interval positive")
        deadline = self._monotonic() + timeout
        while True:
            if self.is_foreground():
                return True
            if self._monotonic() >= deadline:
                return False
            self._sleep(min(poll_interval, max(0, deadline - self._monotonic())))
