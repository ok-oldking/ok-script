import threading
from unittest.mock import Mock

from ok.util.handler import ExitEvent, Handler


def test_handler_thread_stops_synchronously_with_exit_event():
    event = ExitEvent()
    handler = Handler(event, "test-handler-exit")

    event.set()
    handler.join(timeout=1)

    assert not handler.thread.is_alive()


def test_stopped_handler_rejects_new_work():
    event = ExitEvent()
    handler = Handler(event, "test-handler-stop")
    handler.stop()
    handler.join(timeout=1)

    assert handler.post(lambda: None) is None
    assert not handler.thread.is_alive()


def test_exit_event_is_idempotent_and_continues_after_callback_error():
    event = ExitEvent()
    broken = Mock()
    broken.stop.side_effect = RuntimeError("broken stop")
    healthy = Mock()
    event.bind_stop(broken)
    event.bind_stop(healthy)

    event.set()
    event.set()

    broken.stop.assert_called_once_with()
    healthy.stop.assert_called_once_with()


def test_late_bindings_are_woken_immediately():
    event = ExitEvent()
    event.set()
    listener = Mock()
    condition = threading.Condition()

    event.bind_stop(listener)
    event.bind_condition(condition)

    listener.stop.assert_called_once_with()


def test_remove_existing_preserves_scheduled_heap_order():
    event = ExitEvent()
    handler = Handler(event, "test-handler-heap")
    calls = []
    done = threading.Event()

    def replaced():
        calls.append("old")

    def late():
        calls.append("late")
        done.set()

    handler.post(late, delay=.08)
    handler.post(replaced, delay=.04)
    handler.post(lambda: calls.append("first"), delay=.01)
    handler.post(replaced, delay=.02, remove_existing=True)

    assert done.wait(1)
    event.set()
    handler.join(timeout=1)

    assert calls == ["first", "old", "late"]
