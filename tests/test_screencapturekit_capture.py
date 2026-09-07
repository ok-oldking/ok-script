from types import SimpleNamespace
import sys
import threading

import numpy as np
import pytest

from ok.device.capture_methods.screencapturekit import (
    CaptureStreamState,
    PyObjCScreenCaptureKitBackend,
    ScreenCaptureKitCaptureMethod,
    ScreenCaptureKitCaptureError,
    _WindowGeometryPending,
    _rect_components,
    _request_automatic_capture_resolution,
    _surface_rect,
    _with_locked_bgra_pixel_buffer,
)
from ok.device.capture_methods.screencapturekit_core import StreamFrameMetadata
from ok.device.services import PermissionKind, PermissionState, PermissionStatus
from ok.device.window_target import (
    WindowCandidate,
    WindowCoordinateSpace,
    WindowGeometry,
    WindowMatchHints,
    WindowTargetSnapshot,
)
from ok.device.window_target.macos import MacOSWindowDiscovery
from ok.task.exceptions import CaptureException


MAC_POINTS = WindowCoordinateSpace.MACOS_GLOBAL_LOGICAL_POINTS


def test_rect_components_accepts_pyobjc_cgrect_dictionary_bridge():
    bridged_rect = {"X": 0, "Y": 1.5, "Width": 480, "Height": 284}

    assert _rect_components(bridged_rect) == (0.0, 1.5, 480.0, 284.0)
    assert _surface_rect(bridged_rect) == WindowGeometry(0, 1.5, 480, 284)


def test_automatic_capture_resolution_uses_typed_api_when_available():
    calls = []
    typed = SimpleNamespace(setCaptureResolution_=lambda value: calls.append(("typed", value)))
    assert _request_automatic_capture_resolution(
        typed, SimpleNamespace(SCCaptureResolutionAutomatic=0))
    assert calls == [("typed", 0)]

    assert not _request_automatic_capture_resolution(SimpleNamespace(), SimpleNamespace())


def test_stream_metadata_rejects_non_global_content_geometry():
    with pytest.raises(ValueError, match="macOS logical points"):
        StreamFrameMetadata(
            True,
            global_content_geometry=WindowGeometry(0, 0, 10, 10),
        )
    with pytest.raises(ValueError, match="screen_rect_points"):
        StreamFrameMetadata(
            True,
            screen_rect_points=WindowGeometry(0, 0, 10, 10),
        )


class FakeAXValue:
    def __init__(self, value, value_type):
        self.value = value
        self.value_type = value_type


class FakeApplicationServices:
    kAXValueCGPointType = 1
    kAXValueCGSizeType = 2

    def __init__(self, attributes):
        self.attributes = attributes

    def AXUIElementCreateApplication(self, process_id):
        assert process_id == 10
        return "application"

    def AXUIElementCopyAttributeValue(self, element, name, _value):
        key = (element, name)
        if key not in self.attributes:
            return -25205, None
        return 0, self.attributes[key]

    def AXValueGetType(self, value):
        return value.value_type if isinstance(value, FakeAXValue) else 0

    def AXValueGetValue(self, value, value_type, _result):
        assert value_type == value.value_type
        return True, value.value


class FakeAppKit:
    NSWindowStyleMaskTitled = 1

    class NSWindow:
        @staticmethod
        def contentRectForFrameRect_styleMask_(frame, style_mask):
            assert frame == ((0, 0), (960, 568))
            assert style_mask == FakeAppKit.NSWindowStyleMaskTitled
            return ((0, 0), (960, 540))

    @staticmethod
    def NSMakeRect(x, y, width, height):
        return ((x, y), (width, height))


def test_content_region_uses_ax_standard_window_and_top_origin_source_rect():
    backend = object.__new__(PyObjCScreenCaptureKitBackend)
    backend._appkit = FakeAppKit
    backend._application_services = FakeApplicationServices({
        ("application", "AXWindows"): ("window",),
        ("window", "AXPosition"): FakeAXValue(
            SimpleNamespace(x=0, y=213),
            FakeApplicationServices.kAXValueCGPointType,
        ),
        ("window", "AXSize"): FakeAXValue(
            SimpleNamespace(width=960, height=568),
            FakeApplicationServices.kAXValueCGSizeType,
        ),
        ("window", "AXTitle"): "鸣潮  ",
        ("window", "AXSubrole"): "AXStandardWindow",
        ("window", "AXTitleUIElement"): "title-bar",
    })
    selected_window = SimpleNamespace(frame=lambda: ((0, 213), (960, 568)))
    selected = WindowCandidate(
        process_id=10,
        window_id=20,
        bundle_identifier="com.example.game",
        application_name="Example Game",
        title="鸣潮",
        layer=0,
        outer_geometry=WindowGeometry(0, 213, 960, 568, MAC_POINTS),
    )

    local, global_content = backend._content_region(selected, selected_window)

    assert local == WindowGeometry(0, 28, 960, 540)
    assert global_content == WindowGeometry(0, 241, 960, 540, MAC_POINTS)


def test_content_region_fails_closed_when_ax_window_is_not_unique():
    backend = object.__new__(PyObjCScreenCaptureKitBackend)
    backend._application_services = FakeApplicationServices({
        ("application", "AXWindows"): (),
    })
    selected_window = SimpleNamespace(frame=lambda: ((0, 213), (960, 568)))
    selected = WindowCandidate(
        process_id=10,
        window_id=20,
        bundle_identifier="com.example.game",
        application_name="Example Game",
        title="鸣潮",
        layer=0,
        outer_geometry=WindowGeometry(0, 213, 960, 568, MAC_POINTS),
    )

    with pytest.raises(ScreenCaptureKitCaptureError, match="Accessibility permission"):
        backend._content_region(selected, selected_window)


def test_content_region_fails_closed_without_verifiable_title_bar():
    backend = object.__new__(PyObjCScreenCaptureKitBackend)
    backend._appkit = FakeAppKit
    backend._application_services = FakeApplicationServices({
        ("application", "AXWindows"): ("window",),
        ("window", "AXPosition"): FakeAXValue(
            SimpleNamespace(x=0, y=213),
            FakeApplicationServices.kAXValueCGPointType,
        ),
        ("window", "AXSize"): FakeAXValue(
            SimpleNamespace(width=960, height=568),
            FakeApplicationServices.kAXValueCGSizeType,
        ),
        ("window", "AXTitle"): "鸣潮",
        ("window", "AXSubrole"): "AXStandardWindow",
    })
    selected_window = SimpleNamespace(frame=lambda: ((0, 213), (960, 568)))
    selected = WindowCandidate(
        process_id=10,
        window_id=20,
        bundle_identifier="com.example.game",
        application_name="Example Game",
        title="鸣潮",
        layer=0,
        outer_geometry=WindowGeometry(0, 213, 960, 568, MAC_POINTS),
    )

    with pytest.raises(ScreenCaptureKitCaptureError, match="standard title bar"):
        backend._content_region(selected, selected_window)


@pytest.mark.parametrize("failure", ["moving", "duplicate", "missing-titlebar", "nonstandard", "wrong-title"])
def test_content_region_only_retries_identifiable_standard_window_geometry(failure):
    backend = object.__new__(PyObjCScreenCaptureKitBackend)
    backend._appkit = FakeAppKit
    attributes = {
        ("application", "AXWindows"): ("window", "other") if failure == "duplicate" else ("window",),
    }
    for window in ("window", "other"):
        attributes.update({
            (window, "AXPosition"): FakeAXValue(
                SimpleNamespace(x=25, y=213), FakeApplicationServices.kAXValueCGPointType),
            (window, "AXSize"): FakeAXValue(
                SimpleNamespace(width=960, height=568), FakeApplicationServices.kAXValueCGSizeType),
            (window, "AXTitle"): "Other" if failure == "wrong-title" else "Game",
            (window, "AXSubrole"): "AXDialog" if failure == "nonstandard" else "AXStandardWindow",
            (window, "AXTitleUIElement"): None if failure == "missing-titlebar" else "title-bar",
        })
    backend._application_services = FakeApplicationServices(attributes)
    selected = candidate(x=0, y=213, width=960, height=568)
    sc_window = SimpleNamespace(frame=lambda: ((0, 213), (960, 568)))
    with pytest.raises(ScreenCaptureKitCaptureError) as raised:
        backend._content_region(selected, sc_window)
    assert isinstance(raised.value, _WindowGeometryPending) == (failure == "moving")

    if failure == "moving":
        attributes[("window", "AXPosition")] = FakeAXValue(
            SimpleNamespace(x=0, y=213), FakeApplicationServices.kAXValueCGPointType)
        local, content = backend._content_region(selected, sc_window)
        assert local == WindowGeometry(0, 28, 960, 540)
        assert content == WindowGeometry(0, 241, 960, 540, MAC_POINTS)


def test_candidate_and_sc_geometry_disagreement_is_retryable_before_ax_access():
    backend = object.__new__(PyObjCScreenCaptureKitBackend)
    with pytest.raises(_WindowGeometryPending, match="geometry changed"):
        backend._content_region(candidate(), SimpleNamespace(frame=lambda: ((101, 200), (12, 12))))


def candidate(*, x=100, y=200, width=12, height=12, content_geometry=None):
    return WindowCandidate(
        process_id=10,
        window_id=20,
        bundle_identifier='com.example.game',
        application_name='Example Game',
        title='Game',
        layer=0,
        outer_geometry=WindowGeometry(x, y, width, height, MAC_POINTS),
        content_geometry=content_geometry,
    )


class FakeTarget:
    def __init__(self):
        self.snapshot = WindowTargetSnapshot(candidate(), 1, True)
        self.alive = True
        self.refresh_calls = 0

    def exists(self):
        return self.alive

    def refresh(self):
        self.refresh_calls += 1


class FakePermissionService:
    def __init__(
            self,
            state=PermissionState.GRANTED,
            accessibility_state=PermissionState.GRANTED):
        self.state = state
        self.accessibility_state = accessibility_state
        self.calls = 0

    def status(self, kind):
        self.calls += 1
        state = (
            self.state
            if kind is PermissionKind.SCREEN_RECORDING
            else self.accessibility_state)
        return PermissionStatus(
            kind,
            state,
            state is not PermissionState.GRANTED,
            f'System Settings > Privacy & Security > {kind.value}',
        )


class FakeBackend:
    def __init__(self):
        self.starts = []
        self.stops = []
        self.callbacks = []
        self.fail_start = None

    def start_stream(
            self,
            target_snapshot,
            on_sample,
            on_stopped,
            on_sample_error,
            *,
            frames_per_second,
            timeout):
        if self.fail_start:
            raise RuntimeError(self.fail_start)
        binding = SimpleNamespace(number=len(self.starts) + 1)
        self.starts.append((binding, target_snapshot, frames_per_second, timeout))
        self.callbacks.append((on_sample, on_stopped, on_sample_error))
        return binding

    def stop_stream(self, binding, *, timeout):
        self.stops.append((binding, timeout))

    def publish(self, data, *, metadata=None, index=-1, width=12, height=12, stride=48):
        on_sample = self.callbacks[index][0]
        on_sample(
            data,
            width,
            height,
            stride,
            metadata or StreamFrameMetadata(
                True,
                content_rect_points=WindowGeometry(0, 0, width, height),
                display_scale=1.0,
            ),
        )


def make_capture(
        *, permission=None, target=None, backend=None, monotonic=None,
        on_input_invalidated=None):
    return ScreenCaptureKitCaptureMethod(
        threading.Event(),
        target or FakeTarget(),
        permission or FakePermissionService(),
        backend=backend or FakeBackend(),
        lifecycle_timeout=0.1,
        monotonic=monotonic or (lambda: 10.0),
        on_input_invalidated=on_input_invalidated,
    )


def sample(value=1):
    return bytearray([value, value + 1, value + 2, 255] * 144)


class GeometryPendingBackend(FakeBackend):
    pending = True

    def __init__(self):
        super().__init__()
        self.attempts = []

    def start_stream(self, snapshot, *args, **kwargs):
        self.attempts.append(snapshot)
        if self.pending:
            raise _WindowGeometryPending("AX and SC bounds disagree")
        return super().start_stream(snapshot, *args, **kwargs)


@pytest.mark.parametrize("has_old_stream", [False, True])
def test_geometry_pending_retries_fresh_snapshot_without_publishing_stale_frames(has_old_stream):
    now = [10.0]
    target = FakeTarget()
    backend = GeometryPendingBackend()
    backend.pending = not has_old_stream
    invalidations = []
    capture = make_capture(
        target=target, backend=backend, monotonic=lambda: now[0],
        on_input_invalidated=lambda _capture, reason: invalidations.append(reason))
    if has_old_stream:
        backend.publish(sample())
        assert capture.get_frame_packet() is not None
        backend.pending = True
        target.snapshot = WindowTargetSnapshot(candidate(x=110), 2, True)
        assert capture.get_frame_packet() is None
        backend.publish(sample(2))  # A late sample from the detached stream.
    attempts = len(backend.attempts)
    assert capture.get_frame_packet() is None
    assert len(backend.attempts) == attempts
    assert capture.geometry is None
    assert invalidations
    assert capture.diagnostics().rebuilds == 0

    target.snapshot = WindowTargetSnapshot(candidate(x=140), 3, True)
    backend.pending = False
    now[0] += 0.11
    assert capture.get_frame_packet() is None
    assert target.refresh_calls == 1
    assert backend.attempts[-1].generation == 3
    backend.publish(sample(3))
    packet = capture.get_frame_packet()
    assert packet.geometry.target_generation == 3
    assert packet.geometry.outer_geometry.x == 140
    assert capture.diagnostics().rebuilds == int(has_old_stream)
    capture.close()


def test_geometry_retry_budget_does_not_reset_when_target_generation_changes():
    now = [10.0]
    backend = GeometryPendingBackend()
    target = FakeTarget()
    capture = make_capture(target=target, backend=backend, monotonic=lambda: now[0])
    for generation, delay in enumerate((0.11, 0.21, 0.41, 0.81), 2):
        now[0] += delay
        target.snapshot = WindowTargetSnapshot(candidate(x=generation), generation, True)
        assert capture.get_frame_packet() is None
    now[0] += 1.01
    with pytest.raises(ScreenCaptureKitCaptureError, match="retry limit"):
        capture.get_frame_packet()
    attempts = len(backend.attempts)
    assert attempts == 6
    assert capture.diagnostics().state is CaptureStreamState.FATAL
    assert capture.geometry is None
    now[0] += 10
    target.snapshot = WindowTargetSnapshot(candidate(x=180), 10, True)
    with pytest.raises(ScreenCaptureKitCaptureError, match="retry limit"):
        capture.get_frame_packet()
    assert len(backend.attempts) == attempts
    capture.close()


@pytest.mark.parametrize("action", ["close", "invalidate", "stop", "revoke", "deadline"])
def test_geometry_backoff_is_interruptible_and_never_reopens_input(action):
    now = [10.0]
    backend = GeometryPendingBackend()
    permission = FakePermissionService()
    capture = make_capture(backend=backend, permission=permission, monotonic=lambda: now[0])
    if action == "close":
        capture.close()
    elif action == "invalidate":
        capture.invalidate("test cancellation")
    elif action == "stop":
        capture.exit_event.set()
    elif action == "revoke":
        permission.accessibility_state = PermissionState.REVOKED
    now[0] += 5.1 if action == "deadline" else 0.11
    backend.pending = False
    if action in ("revoke", "deadline"):
        with pytest.raises(ScreenCaptureKitCaptureError):
            capture.get_frame_packet()
    else:
        assert capture.get_frame_packet() is None
    assert len(backend.attempts) == 1
    assert capture.geometry is None
    assert capture.diagnostics().storage_size == 0
    capture.close()


def test_capture_invalidation_notifies_input_gate_before_resource_shutdown():
    backend = FakeBackend()
    invalidations = []
    capture = make_capture(
        backend=backend,
        on_input_invalidated=lambda _capture, reason: invalidations.append(reason),
    )

    capture.invalidate("target refresh started")
    assert invalidations[-1] == "target refresh started"
    assert backend.stops

    capture.close()
    assert invalidations[-1] == "ScreenCaptureKit capture closed"


def test_sample_conversion_error_clears_geometry_and_invalidates_input():
    backend = FakeBackend()
    invalidations = []
    capture = make_capture(
        backend=backend,
        on_input_invalidated=lambda _capture, reason: invalidations.append(reason),
    )
    backend.publish(sample(1))
    assert capture.geometry is not None

    backend.callbacks[-1][2]("bad complete sample")

    assert capture.geometry is None
    assert capture.get_frame_packet() is None
    assert invalidations[-1] == "bad complete sample"


def test_stream_is_started_once_and_publishes_latest_owned_bgr_frame():
    backend = FakeBackend()
    capture = make_capture(backend=backend)
    assert len(backend.starts) == 1

    source = sample(1)
    backend.publish(source)
    frame = capture.get_frame()
    source[:3] = b'\xff\xff\xff'

    assert len(backend.starts) == 1
    assert frame.shape == (12, 12, 3)
    assert frame.dtype == np.uint8
    assert frame[0, 0].tolist() == [1, 2, 3]
    assert capture.connected()
    packet = capture.get_frame_packet()
    assert packet.frame is frame
    assert packet.geometry.target_generation == 1


def test_only_complete_frames_are_published_and_storage_stays_one_slot():
    backend = FakeBackend()
    capture = make_capture(backend=backend)
    backend.publish(sample(1), metadata=StreamFrameMetadata(False))
    assert capture.get_frame() is None

    backend.publish(sample(2))
    backend.publish(sample(3))
    assert capture.get_frame()[0, 0].tolist() == [3, 4, 5]
    diagnostics = capture.diagnostics()
    assert diagnostics.frames_received == 3
    assert diagnostics.frames_dropped_incomplete == 1
    assert diagnostics.frames_published == 2
    assert diagnostics.frames_overwritten == 1
    assert diagnostics.storage_size == 1


def test_content_rect_crops_title_bar_or_surface_padding_and_tracks_geometry():
    target = FakeTarget()
    target.snapshot = WindowTargetSnapshot(
        candidate(
            width=11,
            content_geometry=WindowGeometry(110, 230, 11, 11, MAC_POINTS),
        ),
        1,
        True,
    )
    backend = FakeBackend()
    capture = make_capture(target=target, backend=backend)
    raw = bytearray([1, 2, 3, 255] * 144)
    metadata = StreamFrameMetadata(
        True,
        content_rect_points=WindowGeometry(1, 1, 11, 11),
        display_scale=1.0,
        content_scale=1.0,
        global_content_geometry=WindowGeometry(110, 230, 11, 11, MAC_POINTS),
    )
    backend.publish(raw, metadata=metadata)

    assert capture.get_frame().shape == (11, 11, 3)
    assert capture.geometry.content_rect_pixels.x == 1
    assert capture.frame_pixel_to_global_point(5.5, 5.5) == (115.5, 235.5)


def test_target_generation_change_invalidates_old_frame_and_rebuilds_once():
    target = FakeTarget()
    backend = FakeBackend()
    capture = make_capture(target=target, backend=backend)
    old_callback = backend.callbacks[0][0]
    backend.publish(sample(1))
    assert capture.get_frame() is not None

    target.snapshot = WindowTargetSnapshot(candidate(width=5), 2, True)
    assert capture.get_frame() is None
    assert len(backend.starts) == 2
    assert len(backend.stops) == 1

    old_callback(
        sample(2), 12, 12, 48,
        StreamFrameMetadata(
            True,
            content_rect_points=WindowGeometry(0, 0, 12, 12),
            display_scale=1.0,
        ),
    )
    assert capture.get_frame() is None
    diagnostics = capture.diagnostics()
    assert diagnostics.frames_dropped_stale == 1
    assert diagnostics.rebuilds == 1


def test_live_same_size_move_without_screen_rect_rejects_old_frame_and_rebinds_once():
    initial_content = WindowGeometry(100, 202, 12, 10, MAC_POINTS)
    moved_content = WindowGeometry(140, 242, 12, 10, MAC_POINTS)
    initial = candidate(content_geometry=initial_content)

    class LiveGeometrySystem:
        windows = (initial,)

        def enumerate_windows(self, _timeout):
            return self.windows

        def process_exists(self, process_id):
            return process_id == 10

        def window_exists(self, process_id, window_id):
            return any(
                item.runtime_identity == (process_id, window_id)
                for item in self.windows)

        def window_geometry(self, process_id, window_id):
            selected = next((
                item for item in self.windows
                if item.runtime_identity == (process_id, window_id)
            ), None)
            return selected.outer_geometry if selected is not None else None

        def frontmost_process_id(self):
            return 10

        def request_activation(self, _process_id):
            return True

    system = LiveGeometrySystem()
    discovery = MacOSWindowDiscovery(system)
    hints = WindowMatchHints(bundle_identifiers=("com.example.game",))
    target = discovery.bind(initial, hints)
    backend = FakeBackend()
    capture = make_capture(target=target, backend=backend)
    old_callback = backend.callbacks[0][0]
    initial_metadata = StreamFrameMetadata(
        True,
        content_rect_points=WindowGeometry(0, 0, 12, 10),
        display_scale=1.0,
        global_content_geometry=initial_content,
    )
    backend.publish(sample(1), metadata=initial_metadata)
    assert capture.get_frame_packet() is not None

    system.windows = (
        candidate(x=140, y=240, content_geometry=moved_content),)
    assert capture.get_frame_packet() is None
    assert len(backend.starts) == 2
    assert len(backend.stops) == 1

    old_callback(sample(2), 12, 12, 48, initial_metadata)
    assert capture.get_frame_packet() is None
    assert len(backend.starts) == 2

    backend.publish(
        sample(3),
        metadata=StreamFrameMetadata(
            True,
            content_rect_points=WindowGeometry(0, 0, 12, 10),
            display_scale=1.0,
            global_content_geometry=moved_content,
        ),
    )
    packet = capture.get_frame_packet()
    assert packet is not None
    assert packet.geometry.outer_geometry == WindowGeometry(
        140, 240, 12, 12, MAC_POINTS)
    assert packet.geometry.global_content_geometry == moved_content
    assert packet.geometry.frame_pixel_to_global_point(6, 5) == (146, 247)
    assert capture.diagnostics().rebuilds == 1


def test_scale_or_stream_geometry_change_discards_frame_and_rebuilds():
    backend = FakeBackend()
    capture = make_capture(backend=backend)
    backend.publish(sample(1))
    assert capture.get_frame() is not None

    backend.publish(
        sample(2),
        metadata=StreamFrameMetadata(
            True,
            content_rect_points=WindowGeometry(0, 0, 6, 6),
            display_scale=2.0,
        ),
    )

    assert capture.get_frame() is None
    assert len(backend.starts) == 2
    assert len(backend.stops) == 1
    diagnostics = capture.diagnostics()
    assert diagnostics.geometry_invalidations == 1
    assert diagnostics.rebuilds == 1


def test_window_move_screen_rect_discards_old_geometry_and_refreshes_target():
    target = FakeTarget()
    backend = FakeBackend()
    capture = make_capture(target=target, backend=backend)
    original_outer = target.snapshot.candidate.outer_geometry
    backend.publish(
        sample(1),
        metadata=StreamFrameMetadata(
            True,
            content_rect_points=WindowGeometry(0, 0, 12, 12),
            display_scale=1.0,
            screen_rect_points=original_outer,
            global_content_geometry=original_outer,
        ),
    )
    assert capture.get_frame() is not None

    moved_outer = WindowGeometry(140, 240, 12, 12, MAC_POINTS)
    backend.publish(
        sample(2),
        metadata=StreamFrameMetadata(
            True,
            content_rect_points=WindowGeometry(0, 0, 12, 12),
            display_scale=1.0,
            screen_rect_points=moved_outer,
            global_content_geometry=moved_outer,
        ),
    )

    assert capture.get_frame() is None
    assert target.refresh_calls == 1
    assert len(backend.starts) == 2
    assert len(backend.stops) == 1


def test_stop_failure_is_fatal_and_does_not_start_a_second_stream():
    class FailingStopBackend(FakeBackend):
        def stop_stream(self, binding, *, timeout):
            self.stops.append((binding, timeout))
            raise RuntimeError('stop timed out')

    backend = FailingStopBackend()
    capture = make_capture(backend=backend)
    backend.publish(sample(1))
    backend.publish(
        sample(2),
        metadata=StreamFrameMetadata(
            True,
            content_rect_points=WindowGeometry(0, 0, 6, 6),
            display_scale=2.0,
        ),
    )

    with pytest.raises(CaptureException, match='stop failed'):
        capture.get_frame()

    diagnostics = capture.diagnostics()
    assert len(backend.starts) == 1
    assert len(backend.stops) == 1
    assert diagnostics.state is CaptureStreamState.FATAL
    assert diagnostics.storage_size == 0
    assert diagnostics.geometry is None

    with pytest.raises(ScreenCaptureKitCaptureError, match='stop failed'):
        capture.close()
    assert len(backend.stops) == 2
    assert capture.diagnostics().state is CaptureStreamState.FATAL
    assert capture._unconfirmed_stream is backend.starts[0][0]


def test_unexpected_stop_racing_target_rebuild_remains_fatal():
    target = FakeTarget()
    backend = FakeBackend()
    capture = make_capture(target=target, backend=backend)
    target.snapshot = WindowTargetSnapshot(candidate(width=5), 2, True)
    original_detach = capture._detach_stream

    def stop_before_detach():
        backend.callbacks[0][1]('stopped during target rebuild')
        return original_detach()

    capture._detach_stream = stop_before_detach

    with pytest.raises(CaptureException, match='stopped during target rebuild'):
        capture.get_frame()

    assert len(backend.starts) == 1
    assert capture.diagnostics().state is CaptureStreamState.FATAL


def test_explicit_invalidation_rejects_callback_before_target_refresh_finishes():
    backend = FakeBackend()
    capture = make_capture(backend=backend)
    callback = backend.callbacks[0][0]
    capture.invalidate('refresh started')
    callback(
        sample(1), 12, 12, 48,
        StreamFrameMetadata(
            True,
            content_rect_points=WindowGeometry(0, 0, 12, 12),
            display_scale=1.0,
        ),
    )

    assert capture.diagnostics().frames_dropped_stale == 1
    assert capture.get_frame() is None


@pytest.mark.parametrize(
    ('state', 'expected_state'),
    [
        (PermissionState.REQUIRED, CaptureStreamState.PERMISSION_REQUIRED),
        (PermissionState.REVOKED, CaptureStreamState.PERMISSION_REVOKED),
    ],
)
def test_missing_or_revoked_permission_is_explicit_and_does_not_retry(state, expected_state):
    permission = FakePermissionService(state)
    backend = FakeBackend()
    capture = make_capture(permission=permission, backend=backend)

    with pytest.raises(CaptureException, match='permission'):
        capture.get_frame()
    with pytest.raises(CaptureException, match='permission'):
        capture.get_frame()

    assert backend.starts == []
    assert capture.diagnostics().state is expected_state


def test_missing_accessibility_permission_is_actionable_and_does_not_start_stream():
    permission = FakePermissionService(
        accessibility_state=PermissionState.REQUIRED)
    backend = FakeBackend()
    capture = make_capture(permission=permission, backend=backend)

    with pytest.raises(CaptureException, match='accessibility'):
        capture.get_frame()

    assert backend.starts == []
    assert capture.diagnostics().state is CaptureStreamState.PERMISSION_REQUIRED


def test_accessibility_revoked_during_start_is_not_misreported_as_fatal():
    class RevokingPermission(FakePermissionService):
        def status(self, kind):
            if self.calls >= 2 and kind is PermissionKind.ACCESSIBILITY:
                self.accessibility_state = PermissionState.REVOKED
            return super().status(kind)

    permission = RevokingPermission()
    backend = FakeBackend()
    backend.fail_start = 'AX access disappeared during stream start'
    capture = make_capture(permission=permission, backend=backend)

    with pytest.raises(CaptureException, match='accessibility'):
        capture.get_frame()

    assert capture.diagnostics().state is CaptureStreamState.PERMISSION_REVOKED
    assert backend.starts == []


def test_permission_revocation_after_start_stops_stream_and_clears_frame():
    permission = FakePermissionService()
    backend = FakeBackend()
    capture = make_capture(permission=permission, backend=backend)
    backend.publish(sample(1))
    assert capture.get_frame() is not None

    permission.state = PermissionState.REVOKED
    assert not capture.connected()
    with pytest.raises(CaptureException, match='permission'):
        capture.get_frame()

    assert len(backend.stops) == 1
    assert capture.diagnostics().storage_size == 0


def test_target_loss_stops_stream_without_returning_stale_frame():
    target = FakeTarget()
    backend = FakeBackend()
    capture = make_capture(target=target, backend=backend)
    backend.publish(sample(1))
    target.snapshot = WindowTargetSnapshot(None, 2, False)

    assert not capture.connected()
    assert capture.get_frame() is None
    assert len(backend.stops) == 1
    assert capture.diagnostics().state is CaptureStreamState.TARGET_UNAVAILABLE


def test_live_target_check_rejects_stale_snapshot_and_stops_stream():
    target = FakeTarget()
    backend = FakeBackend()
    capture = make_capture(target=target, backend=backend)
    backend.publish(sample(1))
    target.alive = False

    assert capture.get_frame() is None
    assert not capture.connected()
    assert len(backend.stops) == 1
    assert capture.diagnostics().state is CaptureStreamState.TARGET_UNAVAILABLE
    assert capture.diagnostics().storage_size == 0


def test_fatal_start_and_runtime_stop_do_not_tight_retry_same_generation():
    failed_backend = FakeBackend()
    failed_backend.fail_start = 'start denied'
    failed = make_capture(backend=failed_backend)
    with pytest.raises(CaptureException, match='start denied'):
        failed.get_frame()
    with pytest.raises(CaptureException, match='start denied'):
        failed.get_frame()
    assert len(failed_backend.starts) == 0

    backend = FakeBackend()
    capture = make_capture(backend=backend)
    backend.callbacks[0][1]('stream stopped')
    with pytest.raises(CaptureException, match='stream stopped'):
        capture.get_frame()
    assert len(backend.starts) == 1
    assert not capture.connected()


def test_start_failure_after_a_callback_clears_frame_and_geometry():
    class CallbackThenFail(FakeBackend):
        def start_stream(
                self,
                target_snapshot,
                on_sample,
                on_stopped,
                on_sample_error,
                *,
                frames_per_second,
                timeout):
            on_sample(
                sample(1),
                12,
                12,
                48,
                StreamFrameMetadata(
                    True,
                    content_rect_points=WindowGeometry(0, 0, 12, 12),
                    display_scale=1.0,
                ),
            )
            raise RuntimeError('start failed after callback')

    capture = make_capture(backend=CallbackThenFail())
    diagnostics = capture.diagnostics()

    assert diagnostics.state is CaptureStreamState.FATAL
    assert diagnostics.storage_size == 0
    assert diagnostics.geometry is None
    assert capture._size == (0, 0)


def test_stop_callback_racing_stream_start_cannot_restore_running_state():
    class StopsDuringStart(FakeBackend):
        def start_stream(self, *args, **kwargs):
            binding = super().start_stream(*args, **kwargs)
            self.callbacks[-1][1]('stopped during start')
            return binding

    backend = StopsDuringStart()
    capture = make_capture(backend=backend)

    assert capture.diagnostics().state is CaptureStreamState.FATAL
    assert len(backend.stops) == 1
    assert not capture.connected()


def test_diagnostics_report_fps_age_conversion_errors_and_generations():
    clock = iter((1.0, 2.0, 3.0, 5.0))
    backend = FakeBackend()
    capture = make_capture(backend=backend, monotonic=lambda: next(clock))
    backend.publish(sample(1))
    backend.publish(sample(2))
    backend.callbacks[0][2]('bad surface')
    diagnostics = capture.diagnostics()

    assert diagnostics.fps == 0.0
    assert diagnostics.frame_age_seconds is None
    assert diagnostics.frame_conversion_errors == 1
    assert diagnostics.target_generation == 1
    assert diagnostics.capture_generation > 0
    assert diagnostics.geometry is None
    assert capture.get_frame() is None


def test_close_is_idempotent_and_rejects_late_callbacks():
    backend = FakeBackend()
    capture = make_capture(backend=backend)
    callback = backend.callbacks[0][0]
    capture.close()
    capture.close()
    callback(
        sample(1), 12, 12, 48,
        StreamFrameMetadata(
            True,
            content_rect_points=WindowGeometry(0, 0, 12, 12),
            display_scale=1.0,
        ),
    )

    assert len(backend.stops) == 1
    assert capture.diagnostics().state is CaptureStreamState.CLOSED
    assert capture.get_frame() is None


def test_display_scale_uses_matching_nsscreen_backing_scale_factor():
    backend = object.__new__(PyObjCScreenCaptureKitBackend)
    display = SimpleNamespace(
        frame=lambda: ((0, 0), (100, 80)),
        displayID=lambda: 7,
    )
    screen = SimpleNamespace(
        deviceDescription=lambda: {"NSScreenNumber": 7},
        backingScaleFactor=lambda: 2.0,
    )
    backend._appkit = SimpleNamespace(
        NSScreen=SimpleNamespace(screens=lambda: (screen,)))
    content = SimpleNamespace(displays=lambda: (display,))
    window = SimpleNamespace(frame=lambda: ((10, 10), (50, 40)))

    assert backend._display_scale(content, window) == 2.0
    with pytest.raises(ScreenCaptureKitCaptureError, match='display containing'):
        backend._display_scale(
            SimpleNamespace(displays=lambda: (display,)),
            SimpleNamespace(frame=lambda: ((200, 200), (10, 10))),
        )


def test_pixel_buffer_contract_unlocks_after_consumer_error_and_rejects_non_bgra():
    class BaseAddress:
        def as_buffer(self, length):
            assert length == 48
            return memoryview(bytearray(length))

    class FakeQuartz:
        kCVPixelFormatType_32BGRA = 1
        kCVPixelBufferLock_ReadOnly = 2
        pixel_format = 1
        calls = []

        @classmethod
        def CVPixelBufferIsPlanar(cls, _buffer):
            return False

        @classmethod
        def CVPixelBufferGetPixelFormatType(cls, _buffer):
            return cls.pixel_format

        @classmethod
        def CVPixelBufferLockBaseAddress(cls, _buffer, flags):
            cls.calls.append(('lock', flags))
            return 0

        @classmethod
        def CVPixelBufferUnlockBaseAddress(cls, _buffer, flags):
            cls.calls.append(('unlock', flags))

        @staticmethod
        def CVPixelBufferGetWidth(_buffer):
            return 4

        @staticmethod
        def CVPixelBufferGetHeight(_buffer):
            return 3

        @staticmethod
        def CVPixelBufferGetBytesPerRow(_buffer):
            return 16

        @staticmethod
        def CVPixelBufferGetBaseAddress(_buffer):
            return BaseAddress()

    def fail_consumer(*_args):
        raise RuntimeError('consumer failed')

    with pytest.raises(RuntimeError, match='consumer failed'):
        _with_locked_bgra_pixel_buffer(FakeQuartz, object(), fail_consumer)
    assert FakeQuartz.calls == [('lock', 2), ('unlock', 2)]

    FakeQuartz.pixel_format = 9
    with pytest.raises(ScreenCaptureKitCaptureError, match='expected BGRA'):
        _with_locked_bgra_pixel_buffer(FakeQuartz, object(), fail_consumer)
    assert FakeQuartz.calls == [('lock', 2), ('unlock', 2)]


@pytest.mark.skipif(sys.platform != 'darwin', reason='PyObjC adapter check')
def test_pyobjc_callback_classes_are_protocol_backed_and_reusable():
    first = PyObjCScreenCaptureKitBackend()
    second = PyObjCScreenCaptureKitBackend()

    assert first._output_class is second._output_class
    assert first._delegate_class is second._delegate_class
    assert hasattr(first._output_class, 'stream_didOutputSampleBuffer_ofType_')
    assert hasattr(first._delegate_class, 'stream_didStopWithError_')
