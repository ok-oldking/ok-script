"""Thread-safe foreground-only input gate and held-input bookkeeping."""

from __future__ import annotations

from dataclasses import dataclass
import math
import threading
from typing import Callable, TypeVar

from ok.device.services.permissions import PermissionKind
from ok.device.capture_methods.screencapturekit_core import MAX_FRAME_AGE_SECONDS


T = TypeVar("T")


class ForegroundInputError(RuntimeError):
    """A normal input was rejected before posting any event."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class HeldInputSnapshot:
    keys: tuple[int, ...]
    buttons: tuple[str, ...]
    owner: object | None
    target_generation: int | None


class HeldInputState:
    """State mutated under the same lock as ordinary-event validation."""

    def __init__(self, lock: threading.RLock | None = None):
        self.lock = lock or threading.RLock()
        self._keys: set[int] = set()
        self._buttons: set[str] = set()
        self._owner: object | None = None
        self._target_generation: int | None = None

    def begin(self, owner: object, target_generation: int) -> None:
        with self.lock:
            self._owner = owner
            self._target_generation = target_generation

    def has_key(self, key_code: int) -> bool:
        with self.lock:
            return key_code in self._keys

    def hold_key(self, key_code: int) -> None:
        with self.lock:
            self._keys.add(key_code)

    def release_key(self, key_code: int) -> None:
        with self.lock:
            self._keys.discard(key_code)

    def has_button(self, button: str) -> bool:
        with self.lock:
            return button in self._buttons

    def hold_button(self, button: str) -> None:
        with self.lock:
            self._buttons.add(button)

    def release_button(self, button: str) -> None:
        with self.lock:
            self._buttons.discard(button)

    def snapshot(self) -> HeldInputSnapshot:
        with self.lock:
            return HeldInputSnapshot(
                tuple(sorted(self._keys)),
                tuple(sorted(self._buttons)),
                self._owner,
                self._target_generation,
            )

    def clear(self) -> None:
        with self.lock:
            self._keys.clear()
            self._buttons.clear()
            self._owner = None
            self._target_generation = None


class ForegroundGuard:
    """Validate target, permission, capture and generation immediately before input."""

    def __init__(
            self, target, capture, permission_service, *, lock=None,
            stop_requested: Callable[[], bool] | None = None):
        self.target = target
        self.capture = capture
        self.permission_service = permission_service
        self.lock = lock or threading.RLock()
        self._stop_requested = stop_requested or (lambda: False)
        self._open = False
        self._shutdown = False
        self._reason = "MAC_INPUT_GATE_CLOSED"
        self._target_generation: int | None = None
        self._capture_generation: int | None = None

    @property
    def reason(self) -> str:
        with self.lock:
            return self._reason

    @property
    def is_open(self) -> bool:
        with self.lock:
            return self._open and not self._shutdown

    def _validated_geometry_locked(self):
        if self._shutdown:
            raise ForegroundInputError("MAC_INPUT_GATE_CLOSED", self._reason)
        if not self._open:
            raise ForegroundInputError("MAC_INPUT_GATE_CLOSED", self._reason)
        if self._stop_requested():
            raise ForegroundInputError(
                "MAC_INPUT_GATE_CLOSED", "application or executor is stopping")
        try:
            target_exists = bool(self.target.exists())
            snapshot = self.target.snapshot
        except Exception as error:
            raise ForegroundInputError(
                getattr(self.target, "unavailable_code", "MAC_TARGET_UNAVAILABLE"),
                f"failed to verify target: {error}") from error
        if (
                not target_exists
                or not snapshot.exists
                or snapshot.candidate is None
                or snapshot.candidate.process_id <= 0
                or snapshot.candidate.window_id <= 0):
            raise ForegroundInputError(
                getattr(self.target, "unavailable_code", "MAC_TARGET_UNAVAILABLE"),
                "selected macOS target is unavailable")
        for kind, code in (
                (PermissionKind.SCREEN_RECORDING,
                 "MAC_SCREEN_CAPTURE_PERMISSION_REQUIRED"),
                (PermissionKind.ACCESSIBILITY,
                 "MAC_ACCESSIBILITY_PERMISSION_REQUIRED")):
            try:
                permission = self.permission_service.status(kind)
            except Exception as error:
                raise ForegroundInputError(code, str(error)) from error
            if not permission.granted:
                raise ForegroundInputError(
                    code,
                    permission.detail or permission.state.value,
                )
        try:
            frontmost = bool(self.target.is_foreground())
        except Exception as error:
            raise ForegroundInputError(
                "MAC_GAME_NOT_FOREGROUND", str(error)) from error
        # ``is_foreground()`` performs another live target/geometry check. Read
        # the snapshot again so a same-size move discovered by that check cannot
        # pass with the older generation captured above.
        snapshot = self.target.snapshot
        if (
                not snapshot.exists
                or snapshot.candidate is None
                or snapshot.candidate.process_id <= 0
                or snapshot.candidate.window_id <= 0):
            raise ForegroundInputError(
                getattr(self.target, "unavailable_code", "MAC_TARGET_UNAVAILABLE"),
                "selected macOS target is unavailable")
        if not frontmost:
            raise ForegroundInputError(
                "MAC_GAME_NOT_FOREGROUND", "selected game is not frontmost")

        diagnostics = self.capture.diagnostics()
        state = getattr(getattr(diagnostics, "state", None), "value", None)
        geometry = self.capture.geometry
        if state != "running" or geometry is None:
            raise ForegroundInputError(
                "MAC_CAPTURE_STREAM_STOPPED",
                getattr(diagnostics, "last_error", None) or state or "capture unavailable",
            )
        target_generation = snapshot.generation
        if (
                target_generation != self._target_generation
                or diagnostics.target_generation != target_generation
                or geometry.target_generation != target_generation
                or diagnostics.capture_generation != self._capture_generation
                or geometry.capture_generation != self._capture_generation):
            raise ForegroundInputError(
                "MAC_INPUT_GATE_CLOSED", "capture or target geometry generation changed")
        age = getattr(diagnostics, "frame_age_seconds", None)
        sequence = getattr(diagnostics, "frame_sequence", None)
        captured = getattr(diagnostics, "captured_monotonic", None)
        frame_geometry = getattr(diagnostics, "frame_geometry", None)
        if (not isinstance(sequence, int) or sequence <= 0
                or not isinstance(captured, (int, float)) or not math.isfinite(captured)
                or not isinstance(age, (int, float)) or not math.isfinite(age)
                or not 0 <= age <= MAX_FRAME_AGE_SECONDS
                or frame_geometry != geometry):
            raise ForegroundInputError(
                "MAC_CAPTURE_FRAME_STALE",
                "capture heartbeat unavailable or older than 2 seconds; explicitly resume after capture recovers")
        return geometry

    def open(self) -> tuple[int, int]:
        with self.lock:
            if self._shutdown:
                raise ForegroundInputError("MAC_INPUT_GATE_CLOSED", self._reason)
            snapshot = self.target.snapshot
            diagnostics = self.capture.diagnostics()
            self._target_generation = snapshot.generation
            self._capture_generation = diagnostics.capture_generation
            self._open = True
            self._reason = ""
            try:
                self._validated_geometry_locked()
            except Exception:
                self._open = False
                raise
            return self._target_generation, self._capture_generation

    def run_ordinary(self, callback: Callable[[object], T]) -> T:
        with self.lock:
            geometry = self._validated_geometry_locked()
            return callback(geometry)

    def check(self) -> None:
        with self.lock:
            self._validated_geometry_locked()

    def invalidate(self, reason: str, *, shutdown: bool = False) -> bool:
        with self.lock:
            was_open = self._open and not self._shutdown
            self._open = False
            self._shutdown = self._shutdown or shutdown
            self._reason = str(reason)
            return was_open


__all__ = [
    "ForegroundGuard",
    "ForegroundInputError",
    "HeldInputSnapshot",
    "HeldInputState",
]
