"""macOS TCC permission checks using public Quartz/Accessibility APIs."""

from __future__ import annotations

from ok.device.services.permissions import PermissionKind
from ok.platform import MACOS, require_platform


class MacOSPermissionBackend:
    available = True

    def __init__(self):
        require_platform("macOS permission checks", (MACOS,))
        import ApplicationServices
        import Quartz

        self._application_services = ApplicationServices
        self._quartz = Quartz

    def preflight(self, kind: PermissionKind) -> bool:
        if kind is PermissionKind.SCREEN_RECORDING:
            return bool(self._quartz.CGPreflightScreenCaptureAccess())
        if kind is PermissionKind.ACCESSIBILITY:
            return bool(self._application_services.AXIsProcessTrusted())
        raise ValueError(f"unsupported permission kind: {kind!r}")
    def request(self, kind: PermissionKind) -> bool:
        if kind is PermissionKind.SCREEN_RECORDING:
            return bool(self._quartz.CGRequestScreenCaptureAccess())
        if kind is PermissionKind.ACCESSIBILITY:
            options = {
                self._application_services.kAXTrustedCheckOptionPrompt: True,
            }
            return bool(
                self._application_services.AXIsProcessTrustedWithOptions(options))
        raise ValueError(f"unsupported permission kind: {kind!r}")
