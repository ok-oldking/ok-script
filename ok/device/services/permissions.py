"""Permission state contracts for capture and synthetic input providers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
from typing import Protocol

from ok.platform import is_macos


class PermissionKind(str, Enum):
    SCREEN_RECORDING = "screen-recording"
    ACCESSIBILITY = "accessibility"


class PermissionState(str, Enum):
    UNAVAILABLE = "unavailable"
    GRANTED = "granted"
    REQUIRED = "permission-required"
    REQUESTED = "permission-requested"
    REVOKED = "permission-revoked"
    ERROR = "error"


_SETTINGS_PATHS = {
    PermissionKind.SCREEN_RECORDING:
        "System Settings > Privacy & Security > Screen & System Audio Recording",
    PermissionKind.ACCESSIBILITY:
        "System Settings > Privacy & Security > Accessibility",
}


@dataclass(frozen=True)
class PermissionStatus:
    kind: PermissionKind
    state: PermissionState
    can_request: bool
    settings_path: str
    detail: str = ""

    @property
    def granted(self) -> bool:
        return self.state is PermissionState.GRANTED


class PermissionBackend(Protocol):
    available: bool

    def preflight(self, kind: PermissionKind) -> bool: ...

    def request(self, kind: PermissionKind) -> bool: ...


class UnavailablePermissionBackend:
    available = False

    def preflight(self, kind: PermissionKind) -> bool:
        return False

    def request(self, kind: PermissionKind) -> bool:
        return False


class PermissionService:
    """Single-shot permission checks with observable revoke transitions."""

    def __init__(self, backend: PermissionBackend):
        self.backend = backend
        self._seen_granted: set[PermissionKind] = set()
        self._requested: set[PermissionKind] = set()
        self._lock = threading.RLock()

    def status(self, kind: PermissionKind) -> PermissionStatus:
        with self._lock:
            if not self.backend.available:
                return PermissionStatus(
                    kind,
                    PermissionState.UNAVAILABLE,
                    False,
                    _SETTINGS_PATHS[kind],
                    f"{kind.value} permission is unavailable on this platform",
                )
            try:
                granted = bool(self.backend.preflight(kind))
            except Exception as error:
                return PermissionStatus(
                    kind,
                    PermissionState.ERROR,
                    False,
                    _SETTINGS_PATHS[kind],
                    str(error),
                )
            if granted:
                self._seen_granted.add(kind)
                self._requested.discard(kind)
                return PermissionStatus(
                    kind, PermissionState.GRANTED, False, _SETTINGS_PATHS[kind])
            if kind in self._requested:
                state = PermissionState.REQUESTED
                can_request = False
            elif kind in self._seen_granted:
                state = PermissionState.REVOKED
                can_request = True
            else:
                state = PermissionState.REQUIRED
                can_request = True
            return PermissionStatus(
                kind, state, can_request, _SETTINGS_PATHS[kind])

    def request(self, kind: PermissionKind) -> PermissionStatus:
        with self._lock:
            current = self.status(kind)
            if current.granted or not current.can_request:
                return current
            self._requested.add(kind)
            try:
                self.backend.request(kind)
            except Exception as error:
                return PermissionStatus(
                    kind,
                    PermissionState.ERROR,
                    False,
                    _SETTINGS_PATHS[kind],
                    str(error),
                )
            return self.status(kind)

    def snapshot(self) -> tuple[PermissionStatus, PermissionStatus]:
        return (
            self.status(PermissionKind.SCREEN_RECORDING),
            self.status(PermissionKind.ACCESSIBILITY),
        )


def create_permission_service() -> PermissionService:
    if is_macos():
        from ok.device.services.macos_permissions import MacOSPermissionBackend
        return PermissionService(MacOSPermissionBackend())
    return PermissionService(UnavailablePermissionBackend())
