import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ok.device.DeviceManager import DeviceManager
from ok.device.interaction_methods.foreground_safety import ForegroundInputError
from ok.device.interaction_methods.macos_keys import macos_key_code
from ok.device.interaction_methods.quartz import QuartzForegroundInteraction
from test_quartz_foreground_interaction import FakeCapture, FakeTarget, FakePermissionService, FakeSink
from test_screencapturekit_capture import make_capture, sample


@pytest.mark.parametrize('age', [None, float('nan'), float('inf'), -1, 2.001, 120])
def test_missing_invalid_or_stale_heartbeat_blocks_input(age):
    capture = FakeCapture()
    interaction = QuartzForegroundInteraction(capture, FakeTarget(), FakePermissionService(),
                                              event_sink=FakeSink(), monitor_interval=60)
    try:
        interaction.on_run()
        interaction.send_key_down('w')
        capture.frame_age = age
        with pytest.raises(ForegroundInputError, match='MAC_CAPTURE_FRAME_STALE'):
            interaction.send_key_down('a')
        assert not interaction.guard.is_open
        assert not interaction.held_state.snapshot().keys
        assert ('key', macos_key_code('w'), False) in interaction.event_sink.events
        assert ('key', macos_key_code('a'), True) not in interaction.event_sink.events
    finally:
        interaction.on_destroy()


def test_running_stream_stall_watchdog_releases_pauses_and_requires_new_resume_frame():
    now = [10.0]
    capture = make_capture(monotonic=lambda: now[0])
    target = capture.target
    target.is_foreground = lambda: True
    paused = threading.Event()
    manager = SimpleNamespace(executor=SimpleNamespace(pause=Mock(side_effect=paused.set)), exit_event=None)
    sink = FakeSink()
    interaction = QuartzForegroundInteraction(
        capture, target, capture.permission_service, event_sink=sink, monitor_interval=0.005,
        on_invalidated=lambda reason: DeviceManager._on_macos_interaction_invalidated(manager, reason))
    readiness = capture.await_fresh_frame
    def publish(seconds):
        now[0] += seconds
        capture.backend.publish(sample())  # Identical pixels still constitute a new heartbeat.
    capture.await_fresh_frame = lambda: readiness(timeout=1, sleep=publish)
    try:
        interaction.on_run()
        interaction.send_key_down('w')
        interaction.mouse_down(key='left')
        original_sequence = capture.diagnostics().frame_sequence
        now[0] += 120
        assert capture.diagnostics().state.value == 'running'
        assert capture.get_frame_packet() is None
        assert paused.wait(1)
        assert not interaction.guard.is_open
        assert not interaction.held_state.snapshot().keys
        assert not interaction.held_state.snapshot().buttons
        assert ('key', macos_key_code('w'), False) in sink.events
        assert any(event[:3] == ('button', 'left', False) for event in sink.events)
        publish(0.1)
        assert capture.diagnostics().frame_sequence > original_sequence
        assert not interaction.guard.is_open
        for command in (lambda: interaction.send_key_down('a'), lambda: interaction.mouse_down(key='right')):
            with pytest.raises(ForegroundInputError):
                command()
        before_resume = capture.diagnostics().frame_sequence
        interaction.on_run()
        assert capture.diagnostics().frame_sequence > before_resume
        assert interaction.guard.is_open
        assert not interaction.held_state.snapshot().keys
    finally:
        interaction.on_destroy()
        capture.close()
