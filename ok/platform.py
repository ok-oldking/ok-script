"""Small platform-selection helpers used by shared import boundaries.

Concrete operating-system implementations must stay in their platform modules.
This module intentionally imports no Win32 or PyObjC packages.
"""

from __future__ import annotations

import platform as runtime_platform
import sys
from collections.abc import Iterable


WINDOWS = "win32"
MACOS = "darwin"


class PlatformUnavailableError(RuntimeError):
    """Raised when a caller explicitly requests a platform-only capability."""


def is_windows(platform_name: str | None = None) -> bool:
    return (platform_name or sys.platform) == WINDOWS


def is_macos(platform_name: str | None = None) -> bool:
    return (platform_name or sys.platform) == MACOS


def require_platform(
        feature: str,
        supported_platforms: Iterable[str],
        platform_name: str | None = None) -> None:
    """Fail explicitly when *feature* is unavailable on the current platform."""
    current = platform_name or sys.platform
    supported = tuple(supported_platforms)
    if current in supported:
        return
    supported_text = ", ".join(supported)
    raise PlatformUnavailableError(
        f"{feature} is unavailable on platform {current!r}; "
        f"supported platform(s): {supported_text}")


def require_windows(feature: str, platform_name: str | None = None) -> None:
    require_platform(feature, (WINDOWS,), platform_name)


def require_macos_foreground_host(
        feature: str,
        *,
        platform_name: str | None = None,
        machine_name: str | None = None,
        version_string: str | None = None) -> None:
    """Enforce the Apple Silicon and macOS 13+ foreground-MVP baseline."""
    require_platform(feature, (MACOS,), platform_name)
    machine = (
        runtime_platform.machine() if machine_name is None else machine_name
    ).strip().lower()
    if machine != "arm64":
        raise PlatformUnavailableError(
            f"{feature} requires native Apple Silicon arm64; detected {machine!r}")
    version = (
        runtime_platform.mac_ver()[0] if version_string is None else version_string
    ).strip()
    try:
        parts = tuple(int(part) for part in version.split(".")[:2])
        major_minor = parts + (0,) * (2 - len(parts))
    except ValueError as error:
        raise PlatformUnavailableError(
            f"{feature} could not determine a valid macOS version from {version!r}") from error
    if not version or major_minor < (13, 0):
        raise PlatformUnavailableError(
            f"{feature} requires macOS 13.0 or newer; detected {version or 'unknown'}")
