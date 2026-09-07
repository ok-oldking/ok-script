from types import SimpleNamespace
import threading

import pytest

from ok.device.window_target import (
    StableWindowHint,
    WindowCandidate,
    WindowCoordinateSpace,
    WindowGeometry,
    WindowMatchHints,
    WindowRefreshStatus,
    WindowSelectionStatus,
)
from ok.device.window_target.macos import (
    MacOSWindowDiscovery,
    PyObjCMacOSWindowSystem,
    WindowDiscoveryError,
    WindowDiscoveryTimeoutError,
)


def candidate(
        pid, window_id, *, x=0, y=0, width=1280, height=720,
        title="Game", frontmost=False):
    return WindowCandidate(
        process_id=pid,
        window_id=window_id,
        bundle_identifier="com.example.game",
        application_name="Example Game",
        title=title,
        layer=0,
        outer_geometry=WindowGeometry(x, y, width, height),
        frontmost=frontmost,
    )


class FakeMacOSSystem:
    def __init__(self, windows):
        self.windows = tuple(windows)
        self.frontmost_pid = None
        self.alive = {item.process_id for item in windows}
        self.activation_requests = []
        self.enumerations = 0

    def enumerate_windows(self, timeout):
        assert timeout > 0
        self.enumerations += 1
        return self.windows

    def frontmost_process_id(self):
        return self.frontmost_pid

    def process_exists(self, process_id):
        return process_id in self.alive

    def window_exists(self, process_id, window_id):
        return any(
            item.runtime_identity == (process_id, window_id)
            for item in self.windows
        )

    def window_geometry(self, process_id, window_id):
        item = next((
            item for item in self.windows
            if item.runtime_identity == (process_id, window_id)
        ), None)
        return item.outer_geometry if item is not None else None

    def request_activation(self, process_id):
        self.activation_requests.append(process_id)
        return process_id in self.alive


def test_macos_target_refreshes_geometry_and_rebinds_by_stable_identity():
    first = candidate(10, 20)
    system = FakeMacOSSystem([first])
    discovery = MacOSWindowDiscovery(system, discovery_timeout=1)
    hints = WindowMatchHints(bundle_identifiers=("com.example.game",))
    target = discovery.bind(first, hints)

    system.windows = (candidate(10, 20, width=1600),)
    update = target.refresh()
    assert update.status is WindowRefreshStatus.UPDATED
    assert target.generation == 2

    system.windows = (candidate(10, 21, width=1600),)
    rebound = target.refresh()
    assert rebound.status is WindowRefreshStatus.REBOUND
    assert (target.process_id, target.window_id) == (10, 21)
    assert target.generation == 3
    assert system.enumerations == 3


def test_macos_target_fails_closed_when_rebind_is_ambiguous():
    first = candidate(10, 20)
    system = FakeMacOSSystem([first])
    discovery = MacOSWindowDiscovery(system)
    hints = WindowMatchHints(bundle_identifiers=("com.example.game",))
    target = discovery.bind(first, hints)

    system.windows = (candidate(10, 21), candidate(10, 22))
    result = target.refresh()

    assert result.status is WindowRefreshStatus.MANUAL_SELECTION_REQUIRED
    assert not target.exists()
    assert target.snapshot.candidate is None
    assert target.process_id == 0
    assert target.window_id == 0
    assert target.generation == 2
    assert {item.window_id for item in result.candidates} == {21, 22}


def test_activation_request_is_not_treated_as_observed_frontmost():
    first = candidate(10, 20)
    system = FakeMacOSSystem([first])
    discovery = MacOSWindowDiscovery(system)
    target = discovery.bind(
        first,
        WindowMatchHints(bundle_identifiers=("com.example.game",)),
    )

    assert target.request_activation()
    assert system.activation_requests == [10]
    assert not target.wait_for_observed_activation(0)

    system.frontmost_pid = 10
    assert target.wait_for_observed_activation(0)


def test_bind_rechecks_that_selected_window_still_exists():
    first = candidate(10, 20)
    system = FakeMacOSSystem([first])
    discovery = MacOSWindowDiscovery(system)
    system.windows = ()

    with pytest.raises(WindowDiscoveryError, match='disappeared'):
        discovery.bind(
            first,
            WindowMatchHints(bundle_identifiers=('com.example.game',)),
        )


def test_bind_uses_freshly_enumerated_window_metadata():
    first = candidate(10, 20)
    refreshed = candidate(10, 20, width=1600)
    system = FakeMacOSSystem([refreshed])
    discovery = MacOSWindowDiscovery(system)

    target = discovery.bind(
        first,
        WindowMatchHints(bundle_identifiers=('com.example.game',)),
    )

    assert target.outer_geometry == refreshed.outer_geometry
    assert system.enumerations == 1


def test_exists_checks_window_identity_and_clears_stale_runtime_state():
    first = candidate(10, 20)
    system = FakeMacOSSystem([first])
    target = MacOSWindowDiscovery(system).bind(
        first,
        WindowMatchHints(bundle_identifiers=('com.example.game',)),
    )
    system.windows = ()

    assert not target.exists()
    assert target.snapshot.candidate is None
    assert target.generation == 2


def test_exists_invalidates_target_when_liveness_check_raises():
    class FailingLivenessSystem(FakeMacOSSystem):
        fail = False

        def window_geometry(self, process_id, window_id):
            if self.fail:
                raise RuntimeError('Quartz unavailable')
            return super().window_geometry(process_id, window_id)

    first = candidate(10, 20)
    system = FailingLivenessSystem([first])
    discovery = MacOSWindowDiscovery(system)
    target = discovery.bind(
        first,
        WindowMatchHints(bundle_identifiers=('com.example.game',)),
    )
    system.fail = True

    with pytest.raises(WindowDiscoveryError, match='liveness'):
        target.exists()

    assert target.snapshot.candidate is None
    assert target.generation == 2


def test_exists_invalidates_generation_on_same_size_live_window_move():
    first = candidate(10, 20, x=10, y=20)
    system = FakeMacOSSystem([first])
    target = MacOSWindowDiscovery(system).bind(
        first,
        WindowMatchHints(bundle_identifiers=('com.example.game',)),
    )
    system.windows = (candidate(10, 20, x=210, y=120),)

    assert target.exists()
    assert target.generation == 2
    assert target.outer_geometry == WindowGeometry(210, 120, 1280, 720)
    assert system.enumerations == 1


def test_target_is_fail_closed_while_refresh_enumeration_is_blocked():
    class BlockingSystem(FakeMacOSSystem):
        def __init__(self, windows):
            super().__init__(windows)
            self.started = threading.Event()
            self.release = threading.Event()
            self.block = False

        def enumerate_windows(self, timeout):
            if self.block:
                self.started.set()
                assert self.release.wait(timeout)
            return super().enumerate_windows(timeout)

    first = candidate(10, 20)
    system = BlockingSystem([first])
    target = MacOSWindowDiscovery(system, discovery_timeout=1).bind(
        first,
        WindowMatchHints(bundle_identifiers=('com.example.game',)),
    )
    system.block = True
    results = []
    worker = threading.Thread(target=lambda: results.append(target.refresh()))
    worker.start()
    assert system.started.wait(0.5)

    assert not target.exists()
    assert target.snapshot.candidate is None
    assert target.process_id == 0
    assert target.window_id == 0
    assert target.outer_geometry is None
    assert target.generation == 2

    system.release.set()
    worker.join(1)
    assert not worker.is_alive()
    assert results[0].status is WindowRefreshStatus.UNCHANGED
    assert target.exists()
    assert target.generation == 2


def test_refresh_error_invalidates_the_previous_target():
    class FailingSystem(FakeMacOSSystem):
        def enumerate_windows(self, timeout):
            if getattr(self, 'fail', False):
                raise WindowDiscoveryError('enumeration failed')
            return super().enumerate_windows(timeout)

    first = candidate(10, 20)
    target = MacOSWindowDiscovery(FailingSystem([first])).bind(
        first,
        WindowMatchHints(bundle_identifiers=('com.example.game',)),
    )
    target.discovery.system.fail = True

    with pytest.raises(WindowDiscoveryError, match='enumeration failed'):
        target.refresh()

    assert not target.exists()
    assert target.snapshot.candidate is None
    assert target.generation == 2


class FakeApplication:
    def processID(self):
        return 42

    def bundleIdentifier(self):
        return "com.example.game"

    def applicationName(self):
        return "Example Game"


class FakeWindow:
    def owningApplication(self):
        return FakeApplication()

    def windowID(self):
        return 7

    def title(self):
        return "Example Window"

    def windowLayer(self):
        return 0

    def frame(self):
        return ((10, 20), (1280, 720))


class FakeContent:
    def windows(self):
        return [FakeWindow()]


class ImmediateShareableContent:
    @staticmethod
    def getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
            exclude_desktop, on_screen_only, completion):
        assert exclude_desktop is True
        assert on_screen_only is True
        completion(FakeContent(), None)


def make_system(shareable_content):
    system = object.__new__(PyObjCMacOSWindowSystem)
    system._screen_capture_kit = SimpleNamespace(SCShareableContent=shareable_content)
    system.frontmost_process_id = lambda: 42
    return system


def test_pyobjc_adapter_maps_shareable_window_metadata_without_capture_pixels():
    system = make_system(ImmediateShareableContent)

    windows = system.enumerate_windows(0.1)

    assert windows == (WindowCandidate(
        process_id=42,
        window_id=7,
        bundle_identifier="com.example.game",
        application_name="Example Game",
        title="Example Window",
        layer=0,
        outer_geometry=WindowGeometry(
            10, 20, 1280, 720,
            WindowCoordinateSpace.MACOS_GLOBAL_LOGICAL_POINTS),
        content_geometry=None,
        capture_geometry=None,
        display_scale=None,
        frontmost=True,
    ),)


def test_pyobjc_adapter_reports_timeout_and_api_error_explicitly():
    class NeverCompletes:
        @staticmethod
        def getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
                _exclude_desktop, _on_screen_only, _completion):
            return None

    with pytest.raises(WindowDiscoveryTimeoutError):
        make_system(NeverCompletes).enumerate_windows(0.001)

    class Fails:
        @staticmethod
        def getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
                _exclude_desktop, _on_screen_only, completion):
            completion(None, SimpleNamespace(localizedDescription=lambda: "denied"))

    with pytest.raises(WindowDiscoveryError, match="denied"):
        make_system(Fails).enumerate_windows(0.1)


def test_pyobjc_window_exists_checks_window_id_and_owner_pid():
    class FakeQuartz:
        kCGWindowListOptionIncludingWindow = 'including-window'
        kCGWindowNumber = 'window-number'
        kCGWindowOwnerPID = 'owner-pid'
        kCGWindowBounds = 'bounds'
        result = []

        @classmethod
        def CGWindowListCopyWindowInfo(cls, option, window_id):
            assert option == cls.kCGWindowListOptionIncludingWindow
            assert window_id == 7
            return cls.result

    system = object.__new__(PyObjCMacOSWindowSystem)
    system._quartz = FakeQuartz
    FakeQuartz.result = [{
        'window-number': 7,
        'owner-pid': 42,
        'bounds': {'X': 10, 'Y': 20, 'Width': 1280, 'Height': 720},
    }]

    assert system.window_exists(42, 7)
    assert not system.window_exists(43, 7)
    assert system.window_geometry(42, 7) == WindowGeometry(
        10, 20, 1280, 720,
        WindowCoordinateSpace.MACOS_GLOBAL_LOGICAL_POINTS,
    )


def test_frontmost_query_tracks_native_changes_despite_stale_nsworkspace():
    system = object.__new__(PyObjCMacOSWindowSystem)
    current = [42]
    calls = []
    system._workspace = SimpleNamespace(frontmostApplication=lambda: SimpleNamespace(
        processIdentifier=lambda: 42))

    def front(_out):
        calls.append("front")
        return 0, (0, current[0])

    def pid(serial, _out):
        calls.append("pid")
        return 0, serial[1]

    system._application_services = SimpleNamespace(GetFrontProcess=front, GetProcessPID=pid)
    assert system.frontmost_process_id() == 42
    current[0] = 84
    assert system.frontmost_process_id() == 84
    assert calls == ["front", "pid", "front", "pid"]


@pytest.mark.parametrize("front_result,pid_result", [
    ((-600, None), (0, 42)),
    ((0, None), (0, 42)),
    ((0, (0, 42)), (-600, 42)),
    ((0, (0, 42)), (0, None)),
    ((0, (0, 42)), (0, 0)),
    ((0, (0, 42)), (0, -1)),
])
def test_frontmost_query_fails_closed_on_native_failure(front_result, pid_result):
    system = object.__new__(PyObjCMacOSWindowSystem)
    system._workspace = SimpleNamespace(frontmostApplication=lambda: SimpleNamespace(
        processIdentifier=lambda: 42))
    system._application_services = SimpleNamespace(
        GetFrontProcess=lambda _out: front_result,
        GetProcessPID=lambda _serial, _out: pid_result,
    )
    assert system.frontmost_process_id() is None


def test_frontmost_query_surfaces_native_exception_without_fallback():
    system = object.__new__(PyObjCMacOSWindowSystem)

    def fail(_out):
        raise RuntimeError("native query unavailable")

    system._application_services = SimpleNamespace(GetFrontProcess=fail)
    with pytest.raises(WindowDiscoveryError, match="front process"):
        system.frontmost_process_id()


def test_discovery_manual_selection_returns_stable_hint_only():
    item = candidate(10, 20)
    system = FakeMacOSSystem([item])
    discovery = MacOSWindowDiscovery(system)

    result = discovery.select(
        WindowMatchHints(title_patterns=("Game",)),
        stable_hint=StableWindowHint(),
        manual_window_id=20,
    )

    assert result.status is WindowSelectionStatus.SELECTED
    assert result.stable_hint.to_mapping() == {
        "bundle_identifier": "com.example.game",
        "application_name": "Example Game",
        "title": "Game",
    }
