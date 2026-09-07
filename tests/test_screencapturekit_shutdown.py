"""Shutdown contract tests; no window discovery, capture permission, or game."""

import sys
import threading
import time
from types import SimpleNamespace

import pytest

from ok.device.capture_methods.screencapturekit import (
    CaptureStreamState,
    PyObjCScreenCaptureKitBackend,
    ScreenCaptureKitCaptureError,
    ScreenCaptureKitCaptureMethod,
    _PyObjCStreamBinding,
    _StreamShutdownPending,
)
from ok.device.capture_methods.screencapturekit_core import StreamFrameMetadata
from ok.device.services import PermissionState, PermissionStatus
from ok.device.window_target.base import WindowCandidate, WindowGeometry, WindowTargetSnapshot


class FakeDispatch:
    DISPATCH_TIME_NOW = 0

    def __init__(self, calls):
        self.calls = calls
        self.current_label = b"test.main"
        self.wait_result = 0
        self.wait_hook = None
        self.deadlines = []

    def dispatch_queue_get_label(self, _queue):
        return self.current_label

    def dispatch_group_create(self):
        return object()

    def dispatch_group_async(self, _group, _queue, callback):
        self.calls.append("fence")
        callback()

    def dispatch_time(self, _now, remaining_ns):
        self.deadlines.append(remaining_ns)
        return remaining_ns

    def dispatch_group_wait(self, _group, _deadline):
        self.calls.append("drain")
        if self.wait_hook:
            self.wait_hook()
        return self.wait_result


class FakeStream:
    def __init__(self, calls):
        self.calls = calls
        self.remove_error = None
        self.stop_error = None
        self.stop_callback = None
        self.complete_stop = True
        self.remove_hook = None
        self.stop_hook = None

    def removeStreamOutput_type_error_(self, _output, output_type, _error):
        self.calls.append("remove")
        assert output_type == 0
        if self.remove_hook:
            self.remove_hook()
        return self.remove_error is None, self.remove_error

    def stopCaptureWithCompletionHandler_(self, callback):
        self.calls.append("stop")
        self.stop_callback = callback
        if self.stop_hook:
            self.stop_hook()
        if self.complete_stop:
            callback(self.stop_error)


def native_adapter():
    calls = []
    backend = object.__new__(PyObjCScreenCaptureKitBackend)
    backend._dispatch = FakeDispatch(calls)
    backend._screen_capture_kit = SimpleNamespace(SCStreamOutputTypeScreen=0)
    stream = FakeStream(calls)
    binding = _PyObjCStreamBinding(
        stream,
        SimpleNamespace(_callbacks=object()),
        SimpleNamespace(_callback=object()),
        object(),
    )
    return backend, binding, calls


def test_stop_disables_callbacks_removes_output_stops_then_drains_and_is_idempotent():
    backend, binding, calls = native_adapter()

    def callbacks_disabled():
        assert binding.output._callbacks is None
        assert binding.delegate._callback is None

    binding.stream.remove_hook = callbacks_disabled
    backend.stop_stream(binding, timeout=0.1)
    backend.stop_stream(binding, timeout=0.1)
    assert calls == ["remove", "stop", "fence", "drain"]
    assert binding.output_removed and binding.stop_confirmed and binding.drained


@pytest.mark.parametrize("failure", ["remove", "stop", "drain", "stop-timeout"])
def test_each_unconfirmed_shutdown_stage_raises_and_still_attempts_drain(failure):
    backend, binding, calls = native_adapter()
    if failure == "remove":
        binding.stream.remove_error = "output removal denied"
    elif failure == "stop":
        binding.stream.stop_error = "native stop failed"
    elif failure == "drain":
        backend._dispatch.wait_result = 1
    else:
        binding.stream.complete_stop = False
    with pytest.raises(ScreenCaptureKitCaptureError):
        backend.stop_stream(binding, timeout=0.01)
    assert calls == ["remove", "stop", "fence", "drain"]
    assert not binding.drained
    assert binding.output._callbacks is None
    assert binding.delegate._callback is None
    if failure == "stop-timeout":
        assert backend._dispatch.deadlines == [0]


def test_retry_after_late_stop_completion_only_drains_remaining_output_queue():
    backend, binding, calls = native_adapter()
    binding.stream.complete_stop = False
    with pytest.raises(ScreenCaptureKitCaptureError, match="stop timed out"):
        backend.stop_stream(binding, timeout=0.001)
    binding.stream.stop_callback(None)
    backend.stop_stream(binding, timeout=0.1)
    assert calls.count("remove") == calls.count("stop") == 1
    assert calls.count("drain") == 2
    assert binding.drained


def test_retry_after_drain_timeout_never_restarts_the_native_stream():
    backend, binding, calls = native_adapter()
    backend._dispatch.wait_result = 1
    with pytest.raises(ScreenCaptureKitCaptureError, match="queue drain timed out"):
        backend.stop_stream(binding, timeout=0.1)
    backend._dispatch.wait_result = 0
    backend.stop_stream(binding, timeout=0.1)
    assert calls == ["remove", "stop", "fence", "drain", "fence", "drain"]
    assert binding.drained


def test_stop_from_its_output_queue_is_rejected_before_any_native_wait():
    backend, binding, calls = native_adapter()
    backend._dispatch.current_label = b"com.ok-script.screencapturekit.frames"
    with pytest.raises(ScreenCaptureKitCaptureError, match="outside the frame callback queue"):
        backend.stop_stream(binding, timeout=0.1)
    assert calls == []


@pytest.mark.parametrize("failure", ["error", "exception", "timeout", "cleanup"])
def test_native_start_failure_uses_the_same_confirmed_shutdown_path(failure):
    backend, binding, calls = native_adapter()
    selected = SimpleNamespace(
        windowID=20, owningApplication=SimpleNamespace(processID=10))
    backend._shareable_content = lambda _timeout: SimpleNamespace(windows=(selected,))
    backend._display_scale = lambda *_args: 1.0
    backend._content_region = lambda *_args: (WindowGeometry(0, 0, 12, 12),) * 2

    class Configuration:
        def __getattr__(self, _name):
            return lambda *_args: None

    configuration = Configuration()
    backend._screen_capture_kit.SCStreamConfiguration = SimpleNamespace(
        alloc=lambda: SimpleNamespace(init=lambda: configuration))
    backend._screen_capture_kit.SCContentFilter = SimpleNamespace(
        alloc=lambda: SimpleNamespace(initWithDesktopIndependentWindow_=lambda _window: object()))
    backend._screen_capture_kit.SCStream = SimpleNamespace(
        alloc=lambda: SimpleNamespace(initWithFilter_configuration_delegate_=lambda *_args: binding.stream))
    backend._delegate_class = SimpleNamespace(
        alloc=lambda: SimpleNamespace(initWithCallback_=lambda _callback: binding.delegate))
    backend._output_class = SimpleNamespace(
        alloc=lambda: SimpleNamespace(initWithBackend_callbacks_=lambda *_args: binding.output))
    backend._quartz = SimpleNamespace(CGRectMake=lambda *args: args, kCVPixelFormatType_32BGRA=1)
    backend._core_media = SimpleNamespace(CMTimeMake=lambda *_args: object())
    backend._dispatch.dispatch_queue_create = lambda *_args: binding.queue
    binding.stream.addStreamOutput_type_sampleHandlerQueue_error_ = lambda *_args: (True, None)

    def start(callback):
        calls.append("start")
        if failure == "exception":
            raise RuntimeError("native start exception")
        if failure != "timeout":
            callback("native start error")

    binding.stream.startCaptureWithCompletionHandler_ = start
    if failure == "cleanup":
        backend._dispatch.wait_result = 1
    snapshot = WindowTargetSnapshot(WindowCandidate(
        10, 20, "com.example.game", "Example", "Game", 0, WindowGeometry(0, 0, 12, 12)), 1, True)
    with pytest.raises((ScreenCaptureKitCaptureError, RuntimeError)) as raised:
        backend.start_stream(snapshot, lambda *_args: None, lambda *_args: None,
                             lambda *_args: None, frames_per_second=30, timeout=0.01)
    assert calls == ["start", "remove", "stop", "fence", "drain"]
    assert isinstance(raised.value, _StreamShutdownPending) == (failure == "cleanup")
    if failure == "cleanup":
        assert raised.value.binding.stream is binding.stream


def capture_with_backend(backend, *, on_input_invalidated=None):
    candidate = WindowCandidate(
        10, 20, "com.example.game", "Example", "Game", 0,
        WindowGeometry(0, 0, 12, 12),
    )
    target = SimpleNamespace(snapshot=WindowTargetSnapshot(candidate, 1, True))
    target.exists = lambda: True
    permission = SimpleNamespace(status=lambda kind: PermissionStatus(
        kind, PermissionState.GRANTED, False, "test permission"))
    return ScreenCaptureKitCaptureMethod(
        threading.Event(), target, permission, backend=backend,
        lifecycle_timeout=0.1, on_input_invalidated=on_input_invalidated,
    )


class LifecycleBackend:
    def __init__(self):
        self.binding = object()
        self.fail_stop = False
        self.stops = []
        self.starts = 0
        self.fail_start = False

    def start_stream(self, _snapshot, on_sample, on_stopped, _on_error, **_kwargs):
        self.starts += 1
        self.on_sample = on_sample
        self.on_stopped = on_stopped
        if self.fail_start:
            raise _StreamShutdownPending("failed-start cleanup is unconfirmed", self.binding)
        return self.binding

    def stop_stream(self, binding, **_kwargs):
        self.stops.append(binding)
        if self.fail_stop:
            raise ScreenCaptureKitCaptureError("output queue drain timed out")


def test_close_failure_keeps_binding_fatal_and_rejects_old_generation_until_retry():
    backend = LifecycleBackend()
    capture = capture_with_backend(backend)
    backend.fail_stop = True
    with pytest.raises(ScreenCaptureKitCaptureError, match="queue drain timed out"):
        capture.close()
    assert capture.diagnostics().state is CaptureStreamState.FATAL
    assert capture._unconfirmed_stream is backend.binding
    backend.on_sample(
        bytearray([1, 2, 3, 255] * 144), 12, 12, 48,
        StreamFrameMetadata(True, WindowGeometry(0, 0, 12, 12), 1.0),
    )
    assert capture.diagnostics().storage_size == 0
    with pytest.raises(ScreenCaptureKitCaptureError):
        capture.get_frame_packet()
    assert backend.starts == 1
    backend.fail_stop = False
    capture.close()
    capture.close()
    assert backend.stops == [backend.binding, backend.binding]
    assert capture.diagnostics().state is CaptureStreamState.CLOSED
    assert capture._unconfirmed_stream is None


def test_native_fatal_callback_retains_binding_for_close_drain():
    backend = LifecycleBackend()
    capture = capture_with_backend(backend)
    backend.on_stopped("native stream failed")
    assert capture.diagnostics().state is CaptureStreamState.FATAL
    assert capture._unconfirmed_stream is backend.binding
    capture.close()
    assert backend.stops == [backend.binding]
    assert capture._unconfirmed_stream is None


def test_failed_start_cleanup_binding_is_kept_and_drained_by_close():
    backend = LifecycleBackend()
    backend.fail_start = True
    capture = capture_with_backend(backend)
    assert capture.diagnostics().state is CaptureStreamState.FATAL
    assert capture._unconfirmed_stream is backend.binding
    with pytest.raises(ScreenCaptureKitCaptureError, match="cleanup is unconfirmed"):
        capture.get_frame_packet()
    capture.close()
    assert backend.stops == [backend.binding]


def test_capture_close_from_output_queue_rejects_before_lifecycle_lock():
    backend, binding, _calls = native_adapter()
    backend.start_stream = lambda *_args, **_kwargs: binding
    capture = capture_with_backend(backend)
    backend._dispatch.current_label = b"com.ok-script.screencapturekit.frames"
    capture._lifecycle_lock.acquire()
    try:
        with pytest.raises(ScreenCaptureKitCaptureError, match="outside the frame callback queue"):
            capture.close()
    finally:
        capture._lifecycle_lock.release()
        backend._dispatch.current_label = b"test.main"
        capture.close()


@pytest.mark.skipif(sys.platform != "darwin", reason="public libdispatch/PyObjC check")
def test_native_dispatch_fence_waits_for_active_and_queued_callbacks_without_capture():
    import dispatch

    backend, binding, calls = native_adapter()
    backend._dispatch = dispatch
    binding.queue = dispatch.dispatch_queue_create(b"com.ok-script.screencapturekit.frames", None)
    started = threading.Event()
    finish_sample = threading.Event()
    removal_observed = threading.Event()
    stop_observed = threading.Event()
    close_done = threading.Event()
    callback_group = dispatch.dispatch_group_create()
    errors = []

    def active_sample():
        started.set()
        assert finish_sample.wait(2.0)
        calls.append("sample-returned")

    def queued_sample():
        # This sample had not entered Python at the time of output removal.
        assert binding.output._callbacks is None
        calls.append("queued-returned")

    def close():
        try:
            backend.stop_stream(binding, timeout=2.0)
        except Exception as error:
            errors.append(error)
        finally:
            close_done.set()

    binding.stream.remove_hook = removal_observed.set
    binding.stream.stop_hook = stop_observed.set
    dispatch.dispatch_group_async(callback_group, binding.queue, active_sample)
    dispatch.dispatch_group_async(callback_group, binding.queue, queued_sample)
    closer = threading.Thread(target=close)
    try:
        assert started.wait(1.0)
        closer.start()
        assert removal_observed.wait(1.0)
        assert stop_observed.wait(1.0)
        assert not close_done.is_set()
        finish_sample.set()
        assert close_done.wait(2.0)
        assert not errors
        assert binding.drained
        assert calls.index("stop") < calls.index("sample-returned") < calls.index("queued-returned")
    finally:
        finish_sample.set()
        if closer.ident is not None:
            closer.join(3.0)
        assert dispatch.dispatch_group_wait(
            callback_group, dispatch.dispatch_time(dispatch.DISPATCH_TIME_NOW, 2_000_000_000)) == 0


@pytest.mark.skipif(sys.platform != "darwin", reason="PyObjC callback object check")
def test_native_output_and_delegate_accept_cleared_callbacks_without_capture():
    backend = PyObjCScreenCaptureKitBackend()
    output = backend._output_class.alloc().initWithBackend_callbacks_(backend, None)
    delegate = backend._delegate_class.alloc().initWithCallback_(None)
    output.stream_didOutputSampleBuffer_ofType_(None, None, 0)
    delegate.stream_didStopWithError_(None, None)


@pytest.mark.skipif(sys.platform != "darwin", reason="public libdispatch timeout check")
def test_native_dispatch_drain_timeout_is_bounded_and_can_be_retried_without_capture():
    import dispatch

    backend, binding, _calls = native_adapter()
    backend._dispatch = dispatch
    binding.queue = dispatch.dispatch_queue_create(b"com.ok-script.screencapturekit.frames", None)
    finish_sample = threading.Event()
    sample_started = threading.Event()
    group = dispatch.dispatch_group_create()

    def sample():
        sample_started.set()
        finish_sample.wait(2.0)

    dispatch.dispatch_group_async(group, binding.queue, sample)
    try:
        assert sample_started.wait(1.0)
        started = time.monotonic()
        with pytest.raises(ScreenCaptureKitCaptureError, match="queue drain timed out"):
            backend.stop_stream(binding, timeout=0.01)
        assert time.monotonic() - started < 1.0
        assert not binding.drained
    finally:
        finish_sample.set()
        assert dispatch.dispatch_group_wait(
            group, dispatch.dispatch_time(dispatch.DISPATCH_TIME_NOW, 2_000_000_000)) == 0
        backend.stop_stream(binding, timeout=1.0)
    assert binding.drained
