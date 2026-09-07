"""First-start regression using the real executor and foreground interaction."""
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ok.device.DeviceManager import DeviceManager
from ok.device.interaction_methods.foreground_safety import ForegroundInputError
from ok.device.interaction_methods.quartz import QuartzForegroundInteraction
from ok.task.TaskExecutor import TaskExecutor
from ok.task.task import TriggerTask
from ok.util.handler import ExitEvent
from test_quartz_foreground_interaction import FakeCapture, FakeTarget, FakePermissionService, FakeSink


def make_executor():
    executor = object.__new__(TaskExecutor)
    executor.lock = threading.RLock()
    executor.exit_event = ExitEvent()
    interaction = QuartzForegroundInteraction(
        FakeCapture(), FakeTarget(), FakePermissionService(),
        event_sink=FakeSink(), exit_event=executor.exit_event)
    executor.device_manager = SimpleNamespace(interaction=interaction)
    executor.thread = None
    executor.paused = False
    executor.onetime_tasks = []
    executor.scene = None
    task = TriggerTask(executor, Mock())
    task._enabled = True  # persisted/default enabled, not enable() transition
    task.ensure_device_capabilities = Mock()
    executor.trigger_tasks = [task]
    ran = threading.Event()
    executor.execute = lambda: ran.set() if interaction.should_capture() else None
    return executor, interaction, task, ran


def test_default_enabled_trigger_arms_before_executor_thread_without_toggle():
    executor, interaction, task, ran = make_executor()
    original = interaction.on_run
    interaction.on_run = Mock(wraps=original)
    try:
        assert not interaction.should_capture()
        executor.start()
        assert ran.wait(1)
        assert task.enabled
        task.ensure_device_capabilities.assert_called_once()
        interaction.send_key_down('w')
        held = interaction.held_state.snapshot()
        executor.start()
        assert interaction.on_run.call_count == 1
        interaction.on_run()  # another task enable must preserve held ownership
        assert interaction.held_state.snapshot() == held
        executor.stop()
        assert not interaction.should_capture()
        assert not interaction.held_state.snapshot().keys
        with pytest.raises(RuntimeError, match='stopping'):
            executor.start()
    finally:
        interaction.on_destroy()


def test_start_fails_closed_when_activation_is_not_observed():
    executor, interaction, _task, ran = make_executor()
    interaction.target.frontmost = False
    interaction.target.activation_observed = False
    try:
        with pytest.raises(ForegroundInputError):
            executor.start()
        assert executor.thread is None and not ran.is_set()
        assert not interaction.should_capture()
        assert all(event == ('cursor',) for event in interaction.event_sink.events)
    finally:
        interaction.on_destroy()


def test_capability_failure_precedes_arming():
    executor, interaction, task, _ran = make_executor()
    task.ensure_device_capabilities.side_effect = RuntimeError('missing capability')
    try:
        with pytest.raises(RuntimeError, match='missing capability'):
            executor.start()
        assert not interaction.should_capture()
        assert executor.thread is None
    finally:
        interaction.on_destroy()


def test_default_enabled_trigger_reaches_run_in_real_executor_loop():
    executor, interaction, task, ran = make_executor()
    del executor.execute  # Exercise production scheduling, not the startup probe.
    executor.onetime_task_queue = []
    executor.trigger_task_index = -1
    executor._last_frame_time = time.time()
    executor._frame = object()
    executor.basic_options = {'Trigger Interval': 0}
    task.should_trigger = lambda: True
    # Only the frame source is synthetic; guard and executor are production code.
    def frame(**kwargs):
        assert interaction.should_capture()
        return executor._frame
    executor.next_frame = frame
    def run():
        ran.set()
        executor.stop()
        return False
    task.run = run
    try:
        executor.start()
        assert ran.wait(1), 'default enabled trigger never reached run()'
        executor.thread.join(1)
        assert not executor.thread.is_alive()
        assert not interaction.should_capture()
        assert all(event == ('cursor',) for event in interaction.event_sink.events)
    finally:
        executor.stop()
        interaction.on_destroy()


@pytest.mark.parametrize('selected', [True, False])
def test_explicit_macos_start_binds_before_provider_creation(selected):
    manager = object.__new__(DeviceManager)
    manager._require_macos_window_config = Mock()
    manager._device_lifecycle_lock = threading.RLock()
    manager._closing = False
    manager.exit_event = threading.Event()
    manager.window_target = None
    manager.config = {}
    order = []
    def bind():
        order.append('bind')
        return SimpleNamespace(selected=object() if selected else None,
                               status=SimpleNamespace(value='manual-selection-required'))
    manager.bind_macos_window = bind
    manager._do_start_locked = lambda **kwargs: order.append('provider')
    if selected:
        manager.prepare_macos_device()
        assert order == ['bind', 'provider']
        assert manager.config['preferred'] == 'macos'
    else:
        with pytest.raises(RuntimeError, match='select the official game window'):
            manager.prepare_macos_device()
        assert order == ['bind'] and not manager.config
