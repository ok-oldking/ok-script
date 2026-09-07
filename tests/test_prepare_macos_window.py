import importlib.util
from pathlib import Path
import time
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location(
    "prepare_macos_window", Path(__file__).parents[1] / "scripts/prepare_macos_window.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def packet(width=1920, height=1080, generation=1):
    rect = NS(to_dict=lambda: {})
    return NS(frame=NS(shape=(height, width, 3)), captured_monotonic=time.monotonic(),
              geometry=NS(display_scale=2, target_generation=generation,
                          capture_generation=1, outer_geometry=rect,
                          global_content_geometry=rect))


@pytest.fixture
def setup(monkeypatch):
    candidate = NS(runtime_identity=(10, 20))
    target = NS(snapshot=NS(candidate=candidate, exists=True, generation=1),
                is_foreground=Mock(return_value=True), refresh=Mock())
    captures = []

    def factory(*args):
        capture = NS(get_frame_packet=Mock(return_value=packet()), close=Mock(),
                     request_content_size=Mock(return_value={"display_scale": 2}),
                     diagnostics=lambda: NS(last_error="size mismatch"))
        captures.append(capture)
        return capture

    monkeypatch.setattr("ok.platform.require_macos_foreground_host", lambda *args: None)
    monkeypatch.setattr("ok.device.services.create_permission_service",
                        lambda: NS(snapshot=lambda: [NS(granted=True)]))
    monkeypatch.setattr("ok.device.window_target.create_macos_window_discovery",
                        lambda: NS(select=lambda *a, **kw: NS(selected=candidate),
                                   bind=lambda *a: target))
    monkeypatch.setattr("ok.device.capture_methods.screencapturekit.ScreenCaptureKitCaptureMethod", factory)
    return target, captures, factory


def test_default_is_readonly(setup):
    _, captures, _ = setup
    report, code = cli.run(bundle_id="test", window_id=20)
    assert code == 0 and not report["verified"]
    captures[0].request_content_size.assert_not_called()
    captures[0].close.assert_called_once()


def test_matching_apply_is_noop(setup):
    _, captures, _ = setup
    report, code = cli.run(bundle_id="test", window_id=20, apply=True)
    assert code == 0 and report["verified"] and not report["size_request_sent"]
    captures[0].request_content_size.assert_not_called()


def test_startup_wait_timeout_does_not_create_capture(setup):
    target, captures, _ = setup
    target.is_foreground.return_value = False
    report, code = cli.run(bundle_id="test", window_id=20, apply=True, wait_foreground=0.001)
    assert code == 1 and not captures and "超时" in report["error"]


def test_startup_wait_observes_foreground_once(setup):
    target, captures, _ = setup
    target.is_foreground.side_effect = [False, True, True]
    report, code = cli.run(bundle_id="test", window_id=20, apply=True, wait_foreground=1)
    assert code == 0 and report["verified"]
    target.refresh.assert_called_once()
    captures[0].request_content_size.assert_not_called()


def test_apply_verifies_new_capture(setup, monkeypatch):
    _, captures, factory = setup

    def changed(*args):
        result = factory(*args)
        if len(captures) == 1:
            result.get_frame_packet.return_value = packet(1512, 982)
        return result

    monkeypatch.setattr("ok.device.capture_methods.screencapturekit.ScreenCaptureKitCaptureMethod", changed)
    report, code = cli.run(bundle_id="test", window_id=20, apply=True)
    assert code == 0 and report["verified"] and len(captures) == 2
    captures[0].request_content_size.assert_called_once_with(1920, 1080)
    captures[1].close.assert_called_once()
    assert report["after"]["frame_size"] == [1920, 1080]


@pytest.mark.parametrize("apply", [False, True])
def test_cleanup_failure_is_nonzero(setup, monkeypatch, apply):
    _, _, factory = setup

    def broken(*args):
        capture = factory(*args)
        capture.close.side_effect = RuntimeError("drain failed")
        return capture

    monkeypatch.setattr("ok.device.capture_methods.screencapturekit.ScreenCaptureKitCaptureMethod", broken)
    report, code = cli.run(bundle_id="test", window_id=20, apply=apply)
    assert code == 1 and not report["verified"]
    assert report["cleanup_error"] == "drain failed"


@pytest.mark.parametrize("change", ["identity", "focus", "missing"])
def test_recheck_after_get_frame(setup, change):
    target, _, factory = setup
    capture = factory()

    def changed():
        if change == "identity":
            target.snapshot.candidate = NS(runtime_identity=(10, 21))
        elif change == "missing":
            target.snapshot.candidate = None
        else:
            target.is_foreground.return_value = False
        return packet()

    capture.get_frame_packet.side_effect = changed
    with pytest.raises(RuntimeError):
        cli.wait_packet(capture, target, (10, 20), 0.1, foreground=True)


@pytest.mark.parametrize("invalid", ["dimensions", "generation", "stale"])
def test_wrong_or_stale_frame_does_not_verify(setup, invalid):
    target, _, factory = setup
    capture = factory()
    frame = packet()
    if invalid == "dimensions":
        frame = packet(1512, 982)
    elif invalid == "generation":
        frame.geometry.target_generation = 2
    else:
        frame.captured_monotonic -= 5
    capture.get_frame_packet.return_value = frame
    with pytest.raises(RuntimeError, match="所需内容帧"):
        cli.wait_packet(capture, target, (10, 20), 0.001, expected=(1920, 1080))
