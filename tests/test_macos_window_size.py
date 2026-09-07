from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ok.device.capture_methods.screencapturekit import (
    PyObjCScreenCaptureKitBackend, ScreenCaptureKitCaptureMethod,
    ScreenCaptureKitCaptureError,
)
from ok.device.window_target import WindowCandidate, WindowGeometry, WindowTargetSnapshot


def make_backend(scale=2):
    backend = object.__new__(PyObjCScreenCaptureKitBackend)
    candidate = WindowCandidate(
        process_id=10, window_id=20, bundle_identifier="com.example.game",
        application_name="Game", title="Game", layer=0,
        outer_geometry=WindowGeometry(0, 100, 756, 519))
    snapshot = WindowTargetSnapshot(candidate, 1, True)
    target = SimpleNamespace(snapshot=snapshot, is_foreground=Mock(return_value=True))
    window = SimpleNamespace(
        frame=lambda: ((0, 100), (756, 519)), windowID=lambda: 20,
        owningApplication=lambda: SimpleNamespace(processID=lambda: 10))
    backend._shareable_content = Mock(return_value=SimpleNamespace(windows=lambda: [window]))
    backend._content_region = Mock(return_value=(WindowGeometry(0, 28, 756, 491), None))
    backend._matching_ax_window = Mock(return_value="selected-ax")
    backend._display_scale = Mock(return_value=scale)
    backend._ax_attribute = Mock(return_value=False)
    backend._application_services = SimpleNamespace(
        kAXValueCGSizeType=2,
        AXUIElementIsAttributeSettable=Mock(return_value=(0, True)),
        AXValueCreate=Mock(side_effect=lambda kind, value: value),
        AXIsProcessTrusted=Mock(return_value=True),
        AXUIElementSetAttributeValue=Mock(return_value=0))
    backend._quartz = SimpleNamespace(
        CGSizeMake=lambda w, h: (w, h),
        CGPreflightScreenCaptureAccess=Mock(return_value=True))
    return backend, target


def request(backend, target, stopping=False):
    return backend.request_content_size(
        target, 1920, 1080, timeout=1, is_stopping=lambda: stopping)


@pytest.mark.parametrize("scale,expected", [(1, (1920, 1108)), (2, (960, 568)), (1.5, (1280, 748))])
def test_one_ax_request_uses_content_pixels_scale_and_existing_decoration(scale, expected):
    backend, target = make_backend(scale)
    result = request(backend, target)
    backend._application_services.AXUIElementSetAttributeValue.assert_called_once_with(
        "selected-ax", "AXSize", expected)
    assert result["requested_frame_size"] == [1920, 1080]
    assert result["requested_outer_size"] == list(expected)
    assert "verified" not in result  # Setter success is not frame verification.


@pytest.mark.parametrize("failure", ["focus", "late-focus", "permission", "recording", "stopping", "generation", "ax-window", "scale", "readonly", "fullscreen", "missing"])
def test_request_fails_closed_without_ax_write(failure):
    backend, target = make_backend()
    services = backend._application_services
    if failure == "focus":
        target.is_foreground.return_value = False
    elif failure == "late-focus":
        target.is_foreground.side_effect = [True, False]
    elif failure == "permission":
        services.AXIsProcessTrusted.return_value = False
    elif failure == "recording":
        backend._quartz.CGPreflightScreenCaptureAccess.return_value = False
    elif failure == "generation":
        def change_target(*args):
            target.snapshot = replace(target.snapshot, generation=2)
            return (0, True)
        services.AXUIElementIsAttributeSettable.side_effect = change_target
    elif failure == "ax-window":
        backend._matching_ax_window.side_effect = ["selected-ax", "replacement-ax"]
    elif failure == "scale":
        backend._display_scale.side_effect = [2, 1]
    elif failure == "readonly":
        services.AXUIElementIsAttributeSettable.return_value = (0, False)
    elif failure == "fullscreen":
        backend._ax_attribute.return_value = True
    elif failure == "missing":
        backend._shareable_content.return_value = SimpleNamespace(windows=lambda: [])
    with pytest.raises(ScreenCaptureKitCaptureError):
        request(backend, target, stopping=failure == "stopping")
    services.AXUIElementSetAttributeValue.assert_not_called()


def test_setter_error_is_not_retried():
    backend, target = make_backend()
    backend._application_services.AXUIElementSetAttributeValue.return_value = -25205
    with pytest.raises(ScreenCaptureKitCaptureError, match="rejected"):
        request(backend, target)
    assert backend._application_services.AXUIElementSetAttributeValue.call_count == 1


def make_capture():
    capture = object.__new__(ScreenCaptureKitCaptureMethod)
    calls = []
    capture.close = Mock(side_effect=lambda: calls.append("closed"))
    capture.backend = SimpleNamespace(request_content_size=Mock(
        side_effect=lambda *args, **kw: calls.append("requested") or {}))
    capture._permission_status = Mock(return_value=SimpleNamespace(granted=True))
    capture.exit_event = SimpleNamespace(is_set=lambda: False)
    capture.target = object()
    capture.lifecycle_timeout = 1
    return capture, calls


def test_capture_closes_and_checks_permission_before_request():
    capture, calls = make_capture()
    capture.request_content_size(1920, 1080)
    assert calls == ["closed", "requested"]


def test_failed_native_drain_prevents_resize():
    capture, calls = make_capture()
    capture.close.side_effect = ScreenCaptureKitCaptureError("drain failed")
    with pytest.raises(ScreenCaptureKitCaptureError, match="drain failed"):
        capture.request_content_size(1920, 1080)
    capture.backend.request_content_size.assert_not_called()


def test_permission_revoked_after_close_prevents_resize():
    capture, calls = make_capture()
    capture._permission_status.return_value.granted = False
    with pytest.raises(ScreenCaptureKitCaptureError, match="permission"):
        capture.request_content_size(1920, 1080)
    assert calls == ["closed"]


@pytest.mark.parametrize("value", [0, -1, 1.5, float("nan"), True])
def test_invalid_size_does_not_close_or_resize(value):
    capture, calls = make_capture()
    with pytest.raises(ValueError):
        capture.request_content_size(value, 1080)
    assert calls == []
