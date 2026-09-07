"""Platform-neutral desktop window target contracts.

Concrete Win32 and PyObjC implementations live in platform-owned modules.  This
module deliberately imports neither backend so it is safe in shared import
graphs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import math
from typing import Protocol, runtime_checkable


class WindowCoordinateSpace(str, Enum):
    """Coordinate spaces known before the Stage D frame geometry work."""

    UNKNOWN = "unknown"
    MACOS_GLOBAL_LOGICAL_POINTS = "macos-global-logical-points"
    WINDOWS_LEGACY_DESKTOP = "windows-legacy-desktop"
    WINDOWS_LEGACY_CAPTURE = "windows-legacy-capture"


@dataclass(frozen=True)
class WindowGeometry:
    """A rectangle with an explicit coordinate-space label."""

    x: float
    y: float
    width: float
    height: float
    coordinate_space: WindowCoordinateSpace = WindowCoordinateSpace.UNKNOWN

    def __post_init__(self) -> None:
        if not isinstance(self.coordinate_space, WindowCoordinateSpace):
            raise TypeError("coordinate_space must be a WindowCoordinateSpace")
        if not all(math.isfinite(value) for value in (
                self.x, self.y, self.width, self.height)):
            raise ValueError("window geometry values must be finite")
        if self.width < 0 or self.height < 0:
            raise ValueError("window geometry width and height must be non-negative")

    def to_dict(self) -> dict[str, float | str]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "coordinate_space": self.coordinate_space.value,
        }


@dataclass(frozen=True)
class StableWindowHint:
    """Persistable app/window identity that excludes volatile runtime IDs."""

    bundle_identifier: str | None = None
    application_name: str | None = None
    title: str | None = None

    _ALLOWED_KEYS = frozenset({"bundle_identifier", "application_name", "title"})
    _VOLATILE_KEYS = frozenset({
        "pid", "process_id", "window_id", "generation", "outer_geometry",
        "content_geometry", "capture_geometry", "display_scale",
        "coordinate_space",
    })

    def __post_init__(self) -> None:
        for field_name in self._ALLOWED_KEYS:
            value = getattr(self, field_name)
            if value is not None:
                stripped = str(value).strip()
                object.__setattr__(self, field_name, stripped or None)

    @classmethod
    def from_mapping(cls, value: object) -> "StableWindowHint":
        if value in (None, {}):
            return cls()
        if not isinstance(value, Mapping):
            raise TypeError("stable window hint must be a mapping")
        forbidden = sorted(set(value) & cls._VOLATILE_KEYS)
        if forbidden:
            raise ValueError(
                "stable window hint cannot contain volatile fields: "
                + ", ".join(forbidden)
            )
        unknown = sorted(set(value) - cls._ALLOWED_KEYS)
        if unknown:
            raise ValueError(
                "unknown stable window hint fields: " + ", ".join(unknown)
            )
        return cls(**value)

    @property
    def empty(self) -> bool:
        return not any((self.bundle_identifier, self.application_name, self.title))

    @property
    def has_application_identity(self) -> bool:
        return bool(self.bundle_identifier or self.application_name)

    def to_mapping(self) -> dict[str, str]:
        return {
            key: value
            for key in ("bundle_identifier", "application_name", "title")
            if (value := getattr(self, key)) is not None
        }


@dataclass(frozen=True)
class WindowCandidate:
    """One window returned by an operating-system discovery adapter."""

    process_id: int
    window_id: int
    bundle_identifier: str | None
    application_name: str
    title: str
    layer: int
    outer_geometry: WindowGeometry
    content_geometry: WindowGeometry | None = None
    capture_geometry: WindowGeometry | None = None
    display_scale: float | None = None
    frontmost: bool = False

    def __post_init__(self) -> None:
        if self.process_id < 0 or self.window_id < 0:
            raise ValueError("process_id and window_id must be non-negative")
        if self.display_scale is not None and (
                not math.isfinite(self.display_scale)
                or self.display_scale <= 0):
            raise ValueError("display_scale must be finite and positive when known")

    @property
    def runtime_identity(self) -> tuple[int, int]:
        return self.process_id, self.window_id

    @property
    def binding_signature(self) -> tuple[object, ...]:
        """Fields that invalidate frames/coordinates when they change."""
        return (
            self.process_id,
            self.window_id,
            self.outer_geometry,
            self.content_geometry,
            self.capture_geometry,
            self.display_scale,
        )

    def stable_hint(self) -> StableWindowHint:
        return StableWindowHint(
            bundle_identifier=self.bundle_identifier,
            application_name=self.application_name,
            title=self.title,
        )


@dataclass(frozen=True)
class WindowTargetSnapshot:
    candidate: WindowCandidate | None
    generation: int
    exists: bool


class WindowRefreshStatus(str, Enum):
    UNCHANGED = "unchanged"
    UPDATED = "updated"
    REBOUND = "rebound"
    LOST = "lost"
    MANUAL_SELECTION_REQUIRED = "manual-selection-required"


@dataclass(frozen=True)
class WindowRefreshResult:
    status: WindowRefreshStatus
    previous: WindowTargetSnapshot
    current: WindowTargetSnapshot
    candidates: tuple[WindowCandidate, ...] = ()


@runtime_checkable
class DesktopWindowTarget(Protocol):
    """Minimal cross-platform target contract for desktop automation."""

    @property
    def snapshot(self) -> WindowTargetSnapshot: ...

    @property
    def process_id(self) -> int: ...

    @property
    def window_id(self) -> int: ...

    @property
    def bundle_identifier(self) -> str | None: ...

    @property
    def application_name(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def outer_geometry(self) -> WindowGeometry | None: ...

    @property
    def content_geometry(self) -> WindowGeometry | None: ...

    @property
    def capture_geometry(self) -> WindowGeometry | None: ...

    @property
    def display_scale(self) -> float | None: ...

    @property
    def generation(self) -> int: ...

    def exists(self) -> bool: ...

    def is_foreground(self) -> bool: ...

    def request_activation(self) -> bool: ...

    def wait_for_observed_activation(
            self, timeout: float, poll_interval: float = 0.05) -> bool: ...

    def refresh(self) -> WindowRefreshResult: ...


class BaseDesktopWindowTarget:
    """Snapshot bookkeeping shared by concrete target adapters."""

    def __init__(self, candidate: WindowCandidate | None = None):
        self._snapshot = WindowTargetSnapshot(
            candidate=candidate,
            generation=1 if candidate is not None else 0,
            exists=candidate is not None,
        )

    @property
    def snapshot(self) -> WindowTargetSnapshot:
        return self._snapshot

    def _update_candidate(
            self, candidate: WindowCandidate | None, *, exists: bool) -> bool:
        previous = self._snapshot
        retained = candidate if exists else None

        previous_signature = (
            previous.candidate.binding_signature
            if previous.candidate is not None else None
        )
        current_signature = (
            retained.binding_signature if retained is not None else None
        )
        invalidated = (
            previous_signature != current_signature
            or previous.exists != exists
        )
        generation = previous.generation + (1 if invalidated else 0)
        self._snapshot = WindowTargetSnapshot(retained, generation, exists)
        return invalidated

    @property
    def process_id(self) -> int:
        snapshot = self.snapshot
        return snapshot.candidate.process_id if snapshot.candidate else 0

    @property
    def window_id(self) -> int:
        snapshot = self.snapshot
        return snapshot.candidate.window_id if snapshot.candidate else 0

    @property
    def bundle_identifier(self) -> str | None:
        snapshot = self.snapshot
        return snapshot.candidate.bundle_identifier if snapshot.candidate else None

    @property
    def application_name(self) -> str:
        snapshot = self.snapshot
        return snapshot.candidate.application_name if snapshot.candidate else ""

    @property
    def title(self) -> str:
        snapshot = self.snapshot
        return snapshot.candidate.title if snapshot.candidate else ""

    @property
    def outer_geometry(self) -> WindowGeometry | None:
        snapshot = self.snapshot
        return snapshot.candidate.outer_geometry if snapshot.candidate else None

    @property
    def content_geometry(self) -> WindowGeometry | None:
        snapshot = self.snapshot
        return snapshot.candidate.content_geometry if snapshot.candidate else None

    @property
    def capture_geometry(self) -> WindowGeometry | None:
        snapshot = self.snapshot
        return snapshot.candidate.capture_geometry if snapshot.candidate else None

    @property
    def display_scale(self) -> float | None:
        snapshot = self.snapshot
        return snapshot.candidate.display_scale if snapshot.candidate else None

    @property
    def generation(self) -> int:
        return self.snapshot.generation

    def exists(self) -> bool:
        return self.snapshot.exists
