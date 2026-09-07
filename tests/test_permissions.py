from concurrent.futures import ThreadPoolExecutor
import time

from ok.device.services.permissions import (
    PermissionKind,
    PermissionService,
    PermissionState,
    UnavailablePermissionBackend,
)
from ok.device.services.macos_permissions import MacOSPermissionBackend


class FakePermissionBackend:
    available = True

    def __init__(self, granted=False):
        self.granted = granted
        self.requests = []
        self.error = None

    def preflight(self, kind):
        if self.error:
            raise self.error
        return self.granted

    def request(self, kind):
        self.requests.append(kind)
        return self.granted


def test_permission_service_requests_once_without_retry_loop():
    backend = FakePermissionBackend()
    service = PermissionService(backend)

    assert service.status(PermissionKind.SCREEN_RECORDING).state is PermissionState.REQUIRED
    requested = service.request(PermissionKind.SCREEN_RECORDING)

    assert requested.state is PermissionState.REQUESTED
    assert not requested.can_request
    assert backend.requests == [PermissionKind.SCREEN_RECORDING]


def test_permission_service_serializes_concurrent_requests():
    class SlowPermissionBackend(FakePermissionBackend):
        def preflight(self, kind):
            time.sleep(0.01)
            return super().preflight(kind)

    backend = SlowPermissionBackend()
    service = PermissionService(backend)

    with ThreadPoolExecutor(max_workers=8) as executor:
        statuses = tuple(executor.map(
            service.request,
            (PermissionKind.SCREEN_RECORDING,) * 8,
        ))

    assert backend.requests == [PermissionKind.SCREEN_RECORDING]
    assert all(status.state is PermissionState.REQUESTED for status in statuses)
    assert not service.status(PermissionKind.SCREEN_RECORDING).can_request
    assert service.request(PermissionKind.SCREEN_RECORDING).state is PermissionState.REQUESTED
    assert backend.requests == [PermissionKind.SCREEN_RECORDING]


def test_permission_service_observes_granted_then_revoked():
    backend = FakePermissionBackend(granted=True)
    service = PermissionService(backend)

    assert service.status(PermissionKind.ACCESSIBILITY).state is PermissionState.GRANTED
    backend.granted = False
    revoked = service.status(PermissionKind.ACCESSIBILITY)

    assert revoked.state is PermissionState.REVOKED
    assert revoked.can_request
    assert "Accessibility" in revoked.settings_path

    requested = service.request(PermissionKind.ACCESSIBILITY)
    assert requested.state is PermissionState.REQUESTED
    assert not requested.can_request
    assert backend.requests == [PermissionKind.ACCESSIBILITY]

    backend.granted = True
    assert service.status(PermissionKind.ACCESSIBILITY).state is PermissionState.GRANTED
    backend.granted = False
    assert service.status(PermissionKind.ACCESSIBILITY).state is PermissionState.REVOKED


def test_permission_service_exposes_errors_and_unavailable_platforms():
    backend = FakePermissionBackend()
    backend.error = RuntimeError("preflight failed")
    error = PermissionService(backend).status(PermissionKind.SCREEN_RECORDING)

    unavailable = PermissionService(UnavailablePermissionBackend()).status(
        PermissionKind.ACCESSIBILITY)

    assert error.state is PermissionState.ERROR
    assert error.detail == "preflight failed"
    assert unavailable.state is PermissionState.UNAVAILABLE
    assert not unavailable.can_request


def test_macos_backend_maps_public_screen_and_accessibility_apis():
    class FakeQuartz:
        preflight = False
        requests = 0

        @classmethod
        def CGPreflightScreenCaptureAccess(cls):
            return cls.preflight

        @classmethod
        def CGRequestScreenCaptureAccess(cls):
            cls.requests += 1
            return True

    class FakeApplicationServices:
        kAXTrustedCheckOptionPrompt = "prompt"
        trusted = True
        options = None

        @classmethod
        def AXIsProcessTrusted(cls):
            return cls.trusted

        @classmethod
        def AXIsProcessTrustedWithOptions(cls, options):
            cls.options = options
            return cls.trusted

    backend = object.__new__(MacOSPermissionBackend)
    backend._quartz = FakeQuartz
    backend._application_services = FakeApplicationServices

    assert not backend.preflight(PermissionKind.SCREEN_RECORDING)
    assert backend.request(PermissionKind.SCREEN_RECORDING)
    assert FakeQuartz.requests == 1
    assert backend.preflight(PermissionKind.ACCESSIBILITY)
    assert backend.request(PermissionKind.ACCESSIBILITY)
    assert FakeApplicationServices.options == {"prompt": True}
