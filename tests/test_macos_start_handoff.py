import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import ok.core.start_controller as module
from ok.core.start_controller import StartController


def setup_controller(monkeypatch):
    controller = StartController.__new__(StartController)
    controller.exit_event = threading.Event()
    controller._start_cancel = threading.Event()
    controller._handoff_lock = threading.Lock()
    controller._handoff_pending = True
    controller.start_timeout = 30
    controller.starting = False
    target = SimpleNamespace(process_id=10, discovery=SimpleNamespace(system=SimpleNamespace(
        frontmost_process_id=lambda: 10)))
    manager = SimpleNamespace(window_target=target, capture_method=object(),
                              get_preferred_device=lambda: {'device': 'macos'})
    executor = SimpleNamespace(get_all_tasks=lambda: [])
    monkeypatch.setattr(module, 'og', SimpleNamespace(device_manager=manager, executor=executor))
    monkeypatch.setattr(module, 'communicate', SimpleNamespace(
        macos_start_status=SimpleNamespace(emit=Mock()),
        starting_emulator=SimpleNamespace(emit=Mock()), task=SimpleNamespace(emit=Mock())))
    controller._do_start = Mock(return_value=True)
    controller._connect_macos_for_task = Mock()
    controller._wait_for_macos_preparation = Mock()
    return controller, target, executor


def test_foreground_wait_precedes_normal_start_without_activation(monkeypatch):
    controller, target, _ = setup_controller(monkeypatch)
    observed = iter([99, 99, 10])
    target.discovery.system.frontmost_process_id = lambda: next(observed)
    controller._start_cancel.wait = Mock()
    assert controller.do_start()
    assert controller._start_cancel.wait.call_count == 2
    controller._do_start.assert_called_once()


@pytest.mark.parametrize('reason', ['cancel', 'exit', 'timeout', 'unbound', 'query-error'])
def test_failed_handoff_never_starts_or_enqueues(monkeypatch, reason):
    controller, target, _ = setup_controller(monkeypatch)
    target.discovery.system.frontmost_process_id = lambda: 99
    if reason == 'cancel':
        controller.cancel_start()
    elif reason == 'exit':
        controller.exit_event.set()
    elif reason == 'timeout':
        times = iter([0, 31])
        monkeypatch.setattr(module.time, 'monotonic', lambda: next(times))
    elif reason == 'unbound':
        target.process_id = 0
    else:
        target.discovery.system.frontmost_process_id = Mock(side_effect=RuntimeError('unknown'))
    assert not controller.do_start()
    controller._do_start.assert_not_called()
    assert not controller.starting


def test_start_failure_rolls_back_only_newly_enabled_tasks(monkeypatch):
    controller, _, executor = setup_controller(monkeypatch)
    class Task:
        def __init__(self, enabled):
            self._enabled = enabled
            self.exit_after_task = False
            self.executor = SimpleNamespace(remove_onetime_task=Mock())
        @property
        def enabled(self):
            return self._enabled
    new, existing = Task(False), Task(True)
    executor.get_all_tasks = lambda: [new, existing]
    def fail(*args):
        new._enabled = True
        new.exit_after_task = True
        return False
    controller._do_start.side_effect = fail
    assert not controller.do_start(new)
    assert not new.enabled and not new.exit_after_task
    new.executor.remove_onetime_task.assert_called_once_with(new)
    assert existing.enabled
    existing.executor.remove_onetime_task.assert_not_called()


def test_double_click_does_not_queue_second_start(monkeypatch):
    controller, _, _ = setup_controller(monkeypatch)
    controller.handler = Mock()
    controller.start()
    controller.start()
    controller.handler.post.assert_called_once()


def test_cancel_after_handoff_is_not_accepted_as_task_stop(monkeypatch):
    controller, _, _ = setup_controller(monkeypatch)
    def start(*args):
        assert not controller.cancel_start()
        assert not controller._start_cancel.is_set()
        return True
    controller._do_start.side_effect = start
    assert controller.do_start()


def test_failure_restores_existing_paused_task(monkeypatch):
    controller, _, executor = setup_controller(monkeypatch)
    class Task:
        enabled = True
        exit_after_task = False
        _paused = True
        @property
        def paused(self):
            return self._paused
    task = Task()
    executor.get_all_tasks = lambda: [task]
    def fail(*args):
        task._paused = False
        task.exit_after_task = True
        raise RuntimeError('readiness failed')
    controller._do_start.side_effect = fail
    assert not controller.do_start(task)
    assert task.paused and not task.exit_after_task


def test_handoff_does_not_rollback_user_changes_made_while_waiting(monkeypatch):
    controller, _, executor = setup_controller(monkeypatch)
    task = SimpleNamespace(enabled=False, paused=False, exit_after_task=False)
    executor.get_all_tasks = lambda: [task]
    controller._wait_for_macos_foreground = lambda: setattr(task, 'exit_after_task', True)
    controller._do_start.return_value = False
    assert not controller.do_start()
    assert task.exit_after_task


@pytest.mark.parametrize('seconds', [0, 8, 23])
def test_per_task_preparation_waits_without_starting(monkeypatch, seconds):
    controller, _, _ = setup_controller(monkeypatch)
    now = [0.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: now[0])
    controller._start_cancel.wait = lambda delay: now.__setitem__(0, now[0] + delay)
    task = SimpleNamespace(config={'Preparation Seconds': seconds})
    StartController._wait_for_macos_preparation(controller, task)
    assert now[0] == pytest.approx(seconds)
    calls = module.communicate.macos_start_status.emit.call_args_list
    assert calls[0].args[1:] == ('preparation', seconds)
    assert calls[-1].args[1:] == ('preparation', 0)
    remaining = [call.args[2] for call in calls]
    assert remaining == sorted(set(remaining), reverse=True)
    controller._do_start.assert_not_called()


@pytest.mark.parametrize('reason', ['focus', 'cancel', 'exit', 'binding'])
def test_preparation_interruption_never_starts(monkeypatch, reason):
    controller, target, _ = setup_controller(monkeypatch)
    controller._wait_for_macos_preparation = lambda task: StartController._wait_for_macos_preparation(controller, task)
    def interrupt(delay):
        if reason == 'focus':
            target.discovery.system.frontmost_process_id = lambda: 99
        elif reason == 'cancel':
            controller.cancel_start()
        elif reason == 'exit':
            controller.exit_event.set()
        else:
            module.og.device_manager.window_target = None
    controller._start_cancel.wait = interrupt
    assert not controller.do_start(SimpleNamespace(config={'Preparation Seconds': 8}))
    controller._do_start.assert_not_called()


@pytest.mark.parametrize('value', [-1, 301, True, '8', 1.5])
def test_invalid_preparation_rejected(monkeypatch, value):
    controller, _, _ = setup_controller(monkeypatch)
    with pytest.raises(RuntimeError, match='Invalid preparation'):
        StartController._wait_for_macos_preparation(controller, SimpleNamespace(config={'Preparation Seconds': value}))


@pytest.mark.parametrize('failure', [None, 'connect', 'capabilities'])
def test_connect_before_foreground_and_never_bypass_requirements(monkeypatch, failure):
    controller, _, _ = setup_controller(monkeypatch)
    order = []
    def step(name):
        def run(*args, **kwargs):
            order.append(name)
            if failure == name:
                raise RuntimeError(name)
        return run
    manager = module.og.device_manager
    manager.prepare_macos_capture = Mock(side_effect=step('connect'))
    manager.capture_method = object()
    module.communicate.adb_devices = Mock()
    task = SimpleNamespace(ensure_device_capabilities=Mock(side_effect=step('capabilities')))
    controller._connect_macos_for_task = lambda task: StartController._connect_macos_for_task(controller, task)
    controller._wait_for_macos_foreground = Mock(side_effect=step('foreground'))
    assert controller.do_start(task) is (failure is None)
    if failure:
        controller._wait_for_macos_foreground.assert_not_called()
        controller._do_start.assert_not_called()
    else:
        assert order == ['connect', 'capabilities', 'foreground']


def test_cancel_before_connection_does_not_create_provider(monkeypatch):
    controller, _, _ = setup_controller(monkeypatch)
    module.og.device_manager.prepare_macos_capture = Mock()
    controller.cancel_start()
    with pytest.raises(RuntimeError, match='cancelled'):
        StartController._connect_macos_for_task(controller, None)
    module.og.device_manager.prepare_macos_capture.assert_not_called()


@pytest.mark.parametrize('same_provider', [True, False])
def test_start_device_reuses_preparation_only_within_same_attempt(monkeypatch, same_provider):
    controller, _, _ = setup_controller(monkeypatch)
    manager = module.og.device_manager
    manager.capture_method = object()
    manager.prepare_macos_capture = Mock()
    controller._prepared_macos_capture = manager.capture_method if same_provider else object()
    assert StartController.start_device(controller)
    assert manager.prepare_macos_capture.call_count == (0 if same_provider else 1)
