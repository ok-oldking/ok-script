from dataclasses import replace

import pytest

from ok.device.window_target import WindowMatchHints, WindowRefreshStatus
from ok.device.window_target.macos import MacOSWindowDiscovery
from ok.device.interaction_methods.quartz import QuartzForegroundInteraction
from ok.device.interaction_methods.foreground_safety import ForegroundInputError
from ok.device.interaction_methods.macos_keys import macos_key_code
from test_macos_window_target import FakeMacOSSystem, candidate
from test_quartz_foreground_interaction import FakeCapture, FakePermissionService, FakeSink


def make_target():
    first = candidate(10, 20)
    system = FakeMacOSSystem([first])
    system.frontmost_pid = 10
    target = MacOSWindowDiscovery(system).bind(first, WindowMatchHints(
        bundle_identifiers=('com.example.game',), minimum_width=100, minimum_height=100))
    return first, system, target


@pytest.mark.parametrize('new_id', [20, 21])
def test_transient_missing_retains_only_recovery_identity(new_id):
    first, system, target = make_target()
    system.windows = ()
    assert not target.exists()
    assert target.unavailable_code == 'MAC_TARGET_UNAVAILABLE'
    generation = target.generation
    assert target.snapshot.candidate is None
    assert target.process_id == target.window_id == 0
    assert target.outer_geometry is None
    system.windows = (replace(first, window_id=new_id),)
    assert not target.exists()  # A liveness poll may not silently revive a binding.
    result = target.refresh()
    assert result.status is WindowRefreshStatus.REBOUND
    assert target.window_id == new_id and target.generation > generation


def test_confirmed_process_exit_is_terminal_for_existing_binding():
    first, system, target = make_target()
    now = [0.0]
    target._monotonic = lambda: now[0]
    system.process_exit_evidence = lambda pid: (False, False)
    system.alive.clear()
    assert not target.exists()
    assert target.unavailable_code == 'MAC_TARGET_UNAVAILABLE'
    for instant in (0.5, 1.0, 1.5):
        now[0] = instant
        assert not target.exists()
    assert target.unavailable_code == 'MAC_TARGET_EXITED'
    system.alive.update((10, 11))  # Includes PID reuse and a new same-bundle process.
    system.windows = (first, replace(first, process_id=11, window_id=21))
    before = system.enumerations
    assert target.refresh().status is WindowRefreshStatus.LOST
    assert system.enumerations == before
    assert not target.exists() and target.snapshot.candidate is None


@pytest.mark.parametrize('evidence', [(True, True), (True, False), (None, False), (False, None)])
def test_single_appkit_negative_or_conflicting_evidence_never_latches_exit(evidence):
    first, system, target = make_target()
    now = [0.0]
    target._monotonic = lambda: now[0]
    system.process_exit_evidence = lambda pid: evidence
    system.alive.clear()
    system.windows = ()  # No exact bound-window proof, even if PID evidence is positive.
    generation = target.generation
    for instant in (0.0, 0.5, 1.0, 2.0):
        now[0] = instant
        assert not target.exists()
        assert target.unavailable_code == 'MAC_TARGET_UNAVAILABLE'
    system.alive.add(10)
    system.windows = (first,)
    assert target.refresh().status is WindowRefreshStatus.REBOUND
    assert target.generation > generation


def test_appkit_false_with_exact_live_foreground_binding_preserves_generation():
    first, system, target = make_target()
    system.process_exit_evidence = lambda pid: (True, True)
    system.alive.clear()
    before = target.snapshot
    assert target.exists()
    assert target.is_foreground()
    assert target.snapshot == before
    assert not target._process_exited
    system.alive.add(10)
    assert target.exists() and target.snapshot == before


@pytest.mark.parametrize('case', ['posix-only', 'unknown', 'other-frontmost',
                                 'moved', 'missing', 'appkit-exception'])
def test_appkit_negative_incomplete_proof_still_invalidates(case):
    first, system, target = make_target()
    system.process_exit_evidence = lambda pid: (True, True)
    system.alive.clear()
    if case == 'posix-only':
        system.process_exit_evidence = lambda pid: (True, False)
    elif case == 'unknown':
        system.process_exit_evidence = lambda pid: (None, True)
    elif case == 'other-frontmost':
        system.frontmost_pid = 99
    elif case == 'moved':
        system.windows = (replace(first, outer_geometry=replace(first.outer_geometry, x=99)),)
    elif case == 'missing':
        system.windows = ()
    else:
        def fail(pid):
            raise RuntimeError('AppKit unavailable')
        system.process_exists = fail
    assert not target.exists()
    assert target.snapshot.candidate is None
    assert target.unavailable_code == 'MAC_TARGET_UNAVAILABLE'


@pytest.mark.parametrize('fault', [None, 'stale-frame', 'generation', 'focus', 'window', 'permission'])
def test_corroborated_liveness_never_bypasses_production_guard(fault):
    _, system, target = make_target()
    capture = FakeCapture()
    capture.geometry.target_generation = target.generation
    permissions = FakePermissionService()
    sink = FakeSink()
    interaction = QuartzForegroundInteraction(capture, target, permissions,
                                              event_sink=sink, monitor_interval=60)
    try:
        interaction.on_run()
        interaction.send_key_down('w')
        interaction.mouse_down(key='left')
        system.alive.clear()
        system.process_exit_evidence = lambda pid: (True, True)
        if fault == 'stale-frame':
            capture.frame_age = 3.0
        elif fault == 'generation':
            capture.geometry.target_generation += 1
        elif fault == 'focus':
            system.frontmost_pid = 99
        elif fault == 'window':
            system.windows = ()
        elif fault == 'permission':
            permissions.granted = False
        if fault is None:
            interaction.send_key_down('a')
            assert interaction.guard.is_open
            assert ('key', macos_key_code('a'), True) in sink.events
        else:
            with pytest.raises(ForegroundInputError):
                interaction.send_key_down('a')
            assert not interaction.guard.is_open
            assert not interaction.held_state.snapshot().keys
            assert not interaction.held_state.snapshot().buttons
            assert ('key', macos_key_code('a'), True) not in sink.events
            # Subsequent healthy evidence cannot automatically reopen the gate.
            system.alive.add(10)
            with pytest.raises(ForegroundInputError):
                interaction.send_key_down('a')
    finally:
        interaction.on_destroy()


def test_fast_repeated_negative_samples_do_not_confirm_exit_and_positive_resets():
    _, system, target = make_target()
    now = [0.0]
    target._monotonic = lambda: now[0]
    system.process_exit_evidence = lambda pid: (False, False)
    system.alive.clear()
    for _ in range(10):
        assert not target.exists()
    assert target._exit_samples == 0
    system.alive.add(10)
    assert not target.exists()  # Explicit refresh is still required.
    system.alive.clear()
    now[0] = 0.5
    assert not target.exists()
    assert target._exit_samples == 1


@pytest.mark.parametrize('error, expected', [(None, True), (3, False), (1, True), (5, None)])
def test_native_independent_exit_evidence(monkeypatch, error, expected):
    from types import SimpleNamespace
    from ok.device.window_target.macos import PyObjCMacOSWindowSystem
    def kill(pid, signal):
        assert (pid, signal) == (10, 0)
        if error is not None:
            raise OSError(error, 'test')
    monkeypatch.setattr('ok.device.window_target.macos.os.kill', kill)
    system = object.__new__(PyObjCMacOSWindowSystem)
    system._quartz = SimpleNamespace(
        kCGWindowListOptionAll=0, kCGNullWindowID=0, kCGWindowOwnerPID='pid',
        CGWindowListCopyWindowInfo=lambda *args: [{'pid': 10}])
    assert system.process_exit_evidence(10) == (expected, True)


@pytest.mark.parametrize('replacement', ['other-pid', 'other-bundle', 'floating'])
def test_recovery_does_not_take_over_untrusted_or_small_window(replacement):
    first, system, target = make_target()
    system.windows = ()
    assert not target.exists()
    item = {'other-pid': replace(first, process_id=11),
            'other-bundle': replace(first, bundle_identifier='com.other.game'),
            'floating': replace(first, outer_geometry=replace(first.outer_geometry, width=52, height=20))}[replacement]
    system.alive.add(item.process_id)
    system.windows = (item,)
    assert target.refresh().status is WindowRefreshStatus.LOST
    assert target.snapshot.candidate is None


def test_returning_old_title_does_not_disambiguate_two_main_windows_after_loss():
    first, system, target = make_target()
    system.windows = ()
    assert not target.exists()
    system.windows = (first, replace(first, window_id=21, title=''))
    result = target.refresh()
    assert result.status is WindowRefreshStatus.MANUAL_SELECTION_REQUIRED
    assert target.snapshot.candidate is None
    assert {item.window_id for item in result.candidates} == {20, 21}


def test_query_exception_is_unavailable_not_confirmed_process_exit():
    first, system, target = make_target()
    original = system.window_geometry
    def fail(*args):
        raise RuntimeError('query failed')
    system.window_geometry = fail
    with pytest.raises(Exception, match='liveness'):
        target.exists()
    assert target.unavailable_code == 'MAC_TARGET_UNAVAILABLE'
    system.window_geometry = original
    assert target.refresh().status is WindowRefreshStatus.REBOUND


@pytest.mark.parametrize('second_check', [False, True])
@pytest.mark.parametrize('probe', ['window_geometry', 'process_exists'])
def test_single_empty_query_closes_guard_releases_and_rejects_old_generation(second_check, probe):
    first, system, target = make_target()
    capture = FakeCapture()
    capture.geometry.target_generation = target.generation
    sink = FakeSink()
    interaction = QuartzForegroundInteraction(capture, target, FakePermissionService(),
                                              event_sink=sink, monitor_interval=60)
    try:
        interaction.on_run()
        interaction.send_key_down('w')
        interaction.mouse_down(key='left')
        original = getattr(system, probe)
        calls = [0]
        def one_missing(*args):
            calls[0] += 1
            return False if calls[0] == (2 if second_check else 1) else original(*args)
        # None is the missing geometry sentinel; process_exists uses False.
        def missing(*args):
            result = one_missing(*args)
            return None if probe == 'window_geometry' and result is False else result
        setattr(system, probe, missing)
        with pytest.raises(ForegroundInputError, match='MAC_TARGET_UNAVAILABLE'):
            interaction.send_key_down('a')
        assert not interaction.guard.is_open
        assert not interaction.held_state.snapshot().keys
        assert not interaction.held_state.snapshot().buttons
        assert ('key', macos_key_code('w'), False) in sink.events
        assert ('key', macos_key_code('a'), True) not in sink.events
        setattr(system, probe, original)
        target.refresh()
        with pytest.raises(ForegroundInputError):
            interaction.send_key_down('a')
        # A target rebound alone cannot reopen input with the old capture.
        with pytest.raises(ForegroundInputError, match='generation changed'):
            interaction.on_run()
        assert not interaction.guard.is_open
    finally:
        interaction.on_destroy()


@pytest.mark.parametrize('new_id', [20, 21])
def test_explicit_resume_rebuilds_capture_and_waits_fresh_frame_with_empty_held_state(new_id):
    from test_screencapturekit_capture import make_capture, sample, candidate as capture_candidate
    first = capture_candidate(width=960, height=568)
    system = FakeMacOSSystem([first])
    system.frontmost_pid = 10
    target = MacOSWindowDiscovery(system).bind(first, WindowMatchHints(
        bundle_identifiers=('com.example.game',), minimum_width=100, minimum_height=100))
    now = [10.0]
    capture = make_capture(target=target, monotonic=lambda: now[0])
    sink = FakeSink()
    interaction = QuartzForegroundInteraction(capture, target, capture.permission_service,
                                              event_sink=sink, monitor_interval=60)
    ready = capture.await_fresh_frame
    def publish(seconds):
        assert not interaction.guard.is_open
        now[0] += seconds
        capture.backend.publish(sample())
    capture.await_fresh_frame = lambda: ready(timeout=1, sleep=publish)
    try:
        interaction.on_run()
        old_generation = capture.geometry.capture_generation
        interaction.send_key_down('w')
        system.windows = ()
        with pytest.raises(ForegroundInputError, match='MAC_TARGET_UNAVAILABLE'):
            interaction.send_key_down('a')
        assert not interaction.held_state.snapshot().keys
        system.windows = (replace(first, window_id=new_id),)
        # Explicit preparation owns recovery, not Quartz's final handoff.
        capture.wait_until_ready(timeout=1, sleep=publish)
        interaction.on_run()
        assert target.window_id == new_id
        assert capture.geometry.capture_generation > old_generation
        assert capture.geometry.target_generation == target.generation
        assert not interaction.held_state.snapshot().keys
        assert not interaction.held_state.snapshot().buttons
        assert interaction.guard.is_open
        interaction.send_key_down('a')
        assert ('key', macos_key_code('a'), True) in sink.events
    finally:
        interaction.on_destroy()
        capture.close()


@pytest.mark.parametrize('state', ['returned', 'ambiguous', 'exited', 'missing'])
def test_main_start_recovers_existing_target_without_implicit_new_binding(state):
    import threading
    from unittest.mock import Mock
    from ok.device.DeviceManager import DeviceManager
    first, system, target = make_target()
    system.windows = ()
    assert not target.exists()
    if state == 'returned':
        system.windows = (replace(first, window_id=21),)
    elif state == 'ambiguous':
        system.windows = (first, replace(first, window_id=21, title=''))
    elif state == 'exited':
        system.alive.clear()
    manager = DeviceManager.__new__(DeviceManager)
    manager._require_macos_window_config = Mock()
    manager._device_lifecycle_lock = threading.RLock()
    manager._closing = False
    manager.exit_event = threading.Event()
    manager.window_target = target
    manager.config = {}
    manager._invalidate_macos_capture = Mock()
    manager.update_macos_device = Mock()
    manager.bind_macos_window = Mock(side_effect=AssertionError('implicit rebind'))
    manager._do_start_locked = Mock()
    if state == 'returned':
        manager.prepare_macos_device()
        manager._do_start_locked.assert_called_once()
        assert target.window_id == 21
    else:
        with pytest.raises(RuntimeError, match='manually select'):
            manager.prepare_macos_device()
        manager._do_start_locked.assert_not_called()
    assert manager.window_target is target
    manager.bind_macos_window.assert_not_called()
