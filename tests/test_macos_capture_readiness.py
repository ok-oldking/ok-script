"""No hardware input: real capture/readiness and executor against synthetic adapters."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
import threading

import pytest

from ok.device.capture_methods.screencapturekit import CaptureStreamState, ScreenCaptureKitCaptureError
from ok.device.services import PermissionState
from ok.device.window_target import WindowTargetSnapshot
from test_screencapturekit_capture import make_capture, sample, candidate
from test_macos_first_start import make_executor


@pytest.mark.parametrize('failure', [None, 'missing', 'generation', 'rebuild'])
def test_final_fresh_frame_revalidation_never_recovers_provider(failure):
    capture, now, tick = fixture_capture()
    if failure == 'missing':
        capture.target.alive = False
    elif failure == 'generation':
        capture.target.snapshot = WindowTargetSnapshot(candidate(), 2, True)
    elif failure == 'rebuild':
        capture._needs_rebuild = True
    capture.target.refresh = Mock(side_effect=AssertionError('discovery forbidden during input handoff'))
    capture._synchronize_stream = Mock(side_effect=AssertionError('provider recovery forbidden during input handoff'))
    def publish(seconds):
        tick(seconds)
        capture.backend.publish(sample())
    try:
        if failure:
            with pytest.raises(ScreenCaptureKitCaptureError, match='MAC_CAPTURE_NOT_PREPARED'):
                capture.await_fresh_frame(timeout=1, sleep=publish)
        else:
            assert capture.await_fresh_frame(timeout=1, sleep=publish).sequence > 0
        capture.target.refresh.assert_not_called()
        capture._synchronize_stream.assert_not_called()
    finally:
        capture.close()


@pytest.mark.parametrize('manual_window_id', [None, 42])
def test_manager_preparation_owns_bind_provider_and_freshness_without_input(manual_window_id):
    from ok.device.DeviceManager import DeviceManager
    manager = DeviceManager.__new__(DeviceManager)
    manager._device_lifecycle_lock = threading.RLock()
    manager._closing = False
    manager.exit_event = threading.Event()
    order = []
    manager.bind_macos_window = Mock(side_effect=lambda **kwargs: (
        order.append('bind') or SimpleNamespace(selected=object())))
    manager.prepare_macos_device = Mock(side_effect=lambda: order.append('provider'))
    manager.capture_method = SimpleNamespace(wait_until_ready=Mock(
        side_effect=lambda **kwargs: order.append('fresh') or 'packet'))
    manager.interaction = Mock()
    assert manager.prepare_macos_capture(timeout=3, manual_window_id=manual_window_id) == 'packet'
    assert order == (['bind'] if manual_window_id else []) + ['provider', 'fresh']
    manager.capture_method.wait_until_ready.assert_called_once_with(timeout=3)
    manager.interaction.on_run.assert_not_called()


def fixture_capture():
    now = [10.0]
    capture = make_capture(monotonic=lambda: now[0])
    def tick(seconds):
        now[0] += seconds
    return capture, now, tick


def test_readiness_requires_new_frame_not_existing_slot():
    capture, now, tick = fixture_capture()
    capture.backend.publish(sample())
    old = capture.get_frame_packet()
    def publish(seconds):
        tick(seconds)
        capture.backend.publish(sample(5))
    try:
        packet = capture.wait_until_ready(timeout=1, sleep=publish)
        assert packet.sequence > old.sequence
        assert packet.frame[0, 0, 0] == 5
    finally:
        capture.close()


def test_readiness_rebuilds_generation_before_returning_frame():
    capture, now, tick = fixture_capture()
    capture.backend.publish(sample())
    capture.target.snapshot = WindowTargetSnapshot(candidate(x=140), 2, True)
    def publish(seconds):
        tick(seconds)
        capture.backend.publish(sample(6))
    try:
        packet = capture.wait_until_ready(timeout=1, sleep=publish)
        assert packet.geometry.target_generation == 2
        assert capture.diagnostics().rebuilds == 1
        assert packet.geometry == capture.geometry
    finally:
        capture.close()


def test_explicit_readiness_reselects_temporarily_missing_window():
    capture, now, tick = fixture_capture()
    capture.target.alive = False
    capture.target.snapshot = WindowTargetSnapshot(None, 2, False)
    def refresh():
        capture.target.refresh_calls += 1
        if capture.target.refresh_calls == 2:
            capture.target.alive = True
            capture.target.snapshot = WindowTargetSnapshot(replace(candidate(), window_id=21), 3, True)
    capture.target.refresh = refresh
    def publish(seconds):
        tick(seconds)
        if capture.target.alive:
            capture.backend.publish(sample())
    try:
        packet = capture.wait_until_ready(timeout=2, sleep=publish)
        assert packet.geometry.target_generation == 3
        assert capture.target.refresh_calls == 2
    finally:
        capture.close()


@pytest.mark.parametrize('failure', ['stale', 'missing', 'generation', 'permission', 'fatal', 'closed', 'exit'])
def test_readiness_failure_is_bounded_and_never_returns_old_frame(failure):
    capture, now, tick = fixture_capture()
    capture.backend.publish(sample())
    if failure == 'missing':
        capture.target.alive = False
    elif failure == 'permission':
        capture.permission_service.state = PermissionState.REVOKED
    elif failure == 'fatal':
        capture._set_fatal('native failure')
    elif failure == 'closed':
        capture.close()
    elif failure == 'exit':
        capture.exit_event.set()
    def publish(seconds):
        tick(seconds)
        if failure == 'generation':
            capture.backend.publish(sample())
            capture.target.snapshot = WindowTargetSnapshot(candidate(), capture.target.snapshot.generation + 1, True)
    try:
        with pytest.raises(ScreenCaptureKitCaptureError):
            capture.wait_until_ready(timeout=0.4, sleep=publish)
        assert now[0] <= 10.5
    finally:
        capture.close()


@pytest.mark.parametrize('ready', [True, False])
def test_executor_waits_for_readiness_before_guard_open(ready):
    executor, interaction, task, ran = make_executor()
    def preflight():
        assert not interaction.guard.is_open
        assert not ran.is_set()
        if not ready:
            raise ScreenCaptureKitCaptureError('rebuild timeout')
    interaction.capture.await_fresh_frame = Mock(side_effect=preflight)
    try:
        if ready:
            executor.start()
            assert ran.wait(1)
            assert interaction.guard.is_open
        else:
            with pytest.raises(ScreenCaptureKitCaptureError):
                executor.start()
            assert not interaction.guard.is_open
            assert executor.thread is None
            assert not interaction.held_state.snapshot().keys
            assert all(event == ('cursor',) for event in interaction.event_sink.events)
        interaction.capture.await_fresh_frame.assert_called_once()
    finally:
        interaction.on_destroy()


def test_foreground_task_unpause_preserves_paused_state_on_failure():
    executor, interaction, task, ran = make_executor()
    executor.device_manager.capabilities = interaction.capabilities
    task._paused = True
    interaction.capture.await_fresh_frame = Mock(side_effect=ScreenCaptureKitCaptureError('rebuild timeout'))
    try:
        with pytest.raises(ScreenCaptureKitCaptureError):
            task.unpause()
        assert task.paused
        assert not interaction.guard.is_open
        task._enabled = False
        task.unpause()  # Stop button must not start the provider again.
        assert not task.paused
        assert interaction.capture.await_fresh_frame.call_count == 1
    finally:
        interaction.on_destroy()


@pytest.mark.parametrize('queued', [False, True])
@pytest.mark.parametrize('ready', [False, True])
def test_controller_resume_and_queued_start_reach_readiness(monkeypatch, queued, ready):
    from ok.core import start_controller as module
    executor, interaction, task, ran = make_executor()
    executor.device_manager.capabilities = interaction.capabilities
    executor.current_task = object() if queued else task
    executor.paused = True
    executor.pause_start = executor.pause_end_time = 0
    executor.onetime_task_queue = []
    task._paused = not queued
    def preflight():
        assert not interaction.guard.is_open
        if not ready:
            raise ScreenCaptureKitCaptureError('rebuild timeout')
    interaction.capture.await_fresh_frame = Mock(side_effect=preflight)
    controller = module.StartController.__new__(module.StartController)
    controller.start_timeout = 8
    controller._connect_macos_for_task = Mock()
    controller._wait_for_macos_preparation = Mock()
    controller.exit_event = threading.Event()
    controller._start_cancel = threading.Event()
    controller._handoff_lock = threading.Lock()
    controller._handoff_pending = True
    manager = SimpleNamespace(
        capture_method=interaction.capture,
        get_preferred_device=lambda: {'device': 'macos'},
        window_target=SimpleNamespace(process_id=10, discovery=SimpleNamespace(
            system=SimpleNamespace(frontmost_process_id=lambda: 10))))
    events = Mock()
    monkeypatch.setattr(module, 'og', SimpleNamespace(executor=executor, app=None, device_manager=manager))
    monkeypatch.setattr(module, 'communicate', SimpleNamespace(starting_emulator=events, task=Mock(), macos_start_status=Mock()))
    try:
        assert controller.do_start(task) is ready
        interaction.capture.await_fresh_frame.assert_called_once()
        assert interaction.guard.is_open is ready
        assert executor.paused is not ready
        if not ready:
            assert 'Start failed' in events.emit.call_args.args[1]
            assert task.paused is (not queued)
    finally:
        interaction.on_destroy()


def test_task_card_routes_foreground_resume_to_background_controller(monkeypatch):
    from ok import og
    from ok.ui.qt.tasks.TaskCard import TaskCard
    task = SimpleNamespace(enabled=True, paused=True, unpause=Mock(),
                           get_device_capabilities=lambda: SimpleNamespace(foreground_only=True))
    controller = SimpleNamespace(start=Mock())
    monkeypatch.setattr(og, 'app', SimpleNamespace(start_controller=controller))
    card = SimpleNamespace(task=task, setExpand=Mock())
    TaskCard.start_clicked(card)
    controller.start.assert_called_once_with(task)
    task.unpause.assert_not_called()


def test_readiness_uses_real_target_matching_excluding_small_floating_window():
    from ok.device.window_target import WindowMatchHints
    from ok.device.window_target.macos import MacOSWindowDiscovery
    from test_macos_window_target import FakeMacOSSystem
    first = candidate(width=960, height=568)
    system = FakeMacOSSystem([first])
    discovery = MacOSWindowDiscovery(system, discovery_timeout=0.1)
    hints = WindowMatchHints(bundle_identifiers=('com.example.game',), minimum_width=100, minimum_height=100)
    target = discovery.bind(first, hints)
    now = [10.0]
    capture = make_capture(target=target, monotonic=lambda: now[0])
    floating = replace(first, window_id=22, outer_geometry=replace(first.outer_geometry, width=52, height=20))
    replacement = replace(first, window_id=23)
    system.windows = (floating,)
    def tick(seconds):
        now[0] += seconds
        if now[0] >= 10.3:
            system.windows = (floating, replacement)
        capture.backend.publish(sample())
    try:
        packet = capture.wait_until_ready(timeout=2, sleep=tick)
        assert target.window_id == 23
        assert packet.geometry.target_generation == target.snapshot.generation
        assert system.enumerations <= 5
        assert not system.activation_requests
    finally:
        capture.close()


def test_stop_during_readiness_does_not_wait_for_start_lock_or_rearm():
    executor, interaction, task, ran = make_executor()
    entered = threading.Event()
    finish = threading.Event()
    errors = []
    def preflight():
        entered.set()
        assert finish.wait(2)
    interaction.capture.await_fresh_frame = preflight
    def start():
        try:
            executor.start()
        except Exception as error:
            errors.append(error)
    starter = threading.Thread(target=start)
    starter.start()
    try:
        assert entered.wait(1)
        interaction.stop()
        assert not interaction.guard.is_open
        finish.set()
        starter.join(1)
        assert not starter.is_alive()
        assert errors and not ran.is_set()
        assert not interaction.held_state.snapshot().keys
        assert all(event == ('cursor',) for event in interaction.event_sink.events)
    finally:
        finish.set()
        starter.join(2)
        interaction.on_destroy()
