"""Platform-neutral desktop target exports and lazy platform factories."""

from ok.device.window_target.base import (
    BaseDesktopWindowTarget,
    DesktopWindowTarget,
    StableWindowHint,
    WindowCandidate,
    WindowCoordinateSpace,
    WindowGeometry,
    WindowRefreshResult,
    WindowRefreshStatus,
    WindowTargetSnapshot,
)
from ok.device.window_target.diagnostics import candidate_diagnostics
from ok.device.window_target.selection import (
    WindowMatchHints,
    WindowSelectionResult,
    WindowSelectionStatus,
    select_window_candidate,
)
from ok.platform import MACOS, require_platform


def create_macos_window_discovery(**kwargs):
    require_platform("macOS window discovery", (MACOS,))
    from ok.device.window_target.macos import MacOSWindowDiscovery
    return MacOSWindowDiscovery(**kwargs)


__all__ = [
    "BaseDesktopWindowTarget",
    "DesktopWindowTarget",
    "StableWindowHint",
    "WindowCandidate",
    "WindowCoordinateSpace",
    "WindowGeometry",
    "WindowMatchHints",
    "WindowRefreshResult",
    "WindowRefreshStatus",
    "WindowSelectionResult",
    "WindowSelectionStatus",
    "WindowTargetSnapshot",
    "candidate_diagnostics",
    "create_macos_window_discovery",
    "select_window_candidate",
]
