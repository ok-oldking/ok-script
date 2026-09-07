"""Model queued native posts: event creation still sees the previous flags."""

from types import SimpleNamespace

import pytest

from ok.device.interaction_methods.quartz import PyObjCQuartzEventSink, QuartzForegroundInteraction
from test_quartz_foreground_interaction import FakeCapture, FakePermissionService, FakeSink, FakeTarget


class QueuedQuartz:
    kCGHIDEventTap = 0
    kCGEventSourceStateHIDSystemState = 1
    kCGEventSourceStateCombinedSessionState = 0
    kCGScrollEventUnitLine = 1
    kCGMouseButtonLeft, kCGMouseButtonRight, kCGMouseButtonCenter = 0, 1, 2
    kCGEventLeftMouseDown, kCGEventLeftMouseUp = 1, 2
    kCGEventRightMouseDown, kCGEventRightMouseUp = 3, 4
    kCGEventMouseMoved, kCGEventLeftMouseDragged, kCGEventRightMouseDragged = 5, 6, 7
    kCGEventOtherMouseDown, kCGEventOtherMouseUp, kCGEventOtherMouseDragged = 25, 26, 27
    kCGEventFlagMaskShift = 1 << 17
    kCGEventFlagMaskControl = 1 << 18
    kCGEventFlagMaskAlternate = 1 << 19
    kCGEventFlagMaskCommand = 1 << 20
    # Public NX_DEVICE* modifier masks; deliberately retain left/right identity.
    modifiers = {
        56: (kCGEventFlagMaskShift, 2, 4),
        60: (kCGEventFlagMaskShift, 4, 2),
        59: (kCGEventFlagMaskControl, 1, 0x2000),
        62: (kCGEventFlagMaskControl, 0x2000, 1),
        58: (kCGEventFlagMaskAlternate, 0x20, 0x40),
        61: (kCGEventFlagMaskAlternate, 0x40, 0x20),
        55: (kCGEventFlagMaskCommand, 8, 0x10),
        54: (kCGEventFlagMaskCommand, 0x10, 8),
    }

    def __init__(self, flags=0):
        self.flags = flags
        self.queue = []
        self.posts = []
        self.fail_up_once = None

    def CGEventCreateKeyboardEvent(self, _source, code, down):
        flags = self.flags
        if code in self.modifiers:
            aggregate, side, other = self.modifiers[code]
            if down:
                flags |= aggregate | side
            else:
                flags &= ~side
                if not flags & other:
                    flags &= ~aggregate
        return {"kind": "key", "code": code, "down": down, "flags": flags}

    def CGEventCreateMouseEvent(self, _source, kind, point, button):
        return {"kind": kind, "point": point, "button": button, "flags": self.flags}

    def CGEventCreateScrollWheelEvent(self, _source, _unit, _axes, amount):
        return {"kind": "scroll", "amount": amount, "flags": self.flags}

    def CGEventSourceKeyState(self, _source, code):
        return bool(self.flags & self.modifiers[code][1])

    @staticmethod
    def CGEventCreate(_source):
        return object()

    @staticmethod
    def CGEventGetLocation(_event):
        return SimpleNamespace(x=100.0, y=100.0)

    @staticmethod
    def CGEventGetFlags(event):
        return event["flags"]

    @staticmethod
    def CGEventSetFlags(event, flags):
        event["flags"] = flags

    def CGEventPost(self, _tap, event):
        if (event["kind"] == "key" and not event["down"]
                and event["code"] == self.fail_up_once):
            self.fail_up_once = None
            raise RuntimeError("release failed once")
        self.queue.append(dict(event))
        self.posts.append(dict(event))

    def drain(self):
        for event in self.queue:
            self.flags = event["flags"]
        self.queue.clear()


@pytest.mark.parametrize("keys", [("shift",), ("shift", "f2"), ("shift", "alt"),
                                  ("lshift", "rshift")])
def test_release_all_does_not_reintroduce_owned_modifiers(keys):
    q = QueuedQuartz()
    value = QuartzForegroundInteraction(
        FakeCapture(), FakeTarget(), FakePermissionService(), event_sink=FakeSink())
    value.event_sink = PyObjCQuartzEventSink(value.guard.check, quartz=q)
    value.on_run()
    try:
        for key in keys:
            value.send_key_down(key)
            q.drain()
        value.mouse_down(key="right")
        value.mouse_down(key="middle")
        q.drain()
        value.stop()
        q.drain()
        assert q.flags == 0
        assert value.held_state.snapshot().keys == ()
        assert value.held_state.snapshot().buttons == ()
    finally:
        value.on_destroy()


@pytest.fixture
def queued_interaction():
    q = QueuedQuartz()
    value = QuartzForegroundInteraction(
        FakeCapture(), FakeTarget(), FakePermissionService(), event_sink=FakeSink())
    value.event_sink = PyObjCQuartzEventSink(value.guard.check, quartz=q)
    value.on_run()
    yield value, q
    value.on_destroy()


@pytest.mark.parametrize("next_event", ["mouse-up", "key-up", "key-down", "move", "scroll"])
def test_normal_modifier_up_cannot_be_reintroduced_by_next_event(queued_interaction, next_event):
    value, q = queued_interaction
    value.send_key_down("shift")
    value.send_key_down("f2")
    value.mouse_down(key="right")
    q.drain()
    value.send_key_up("shift")  # Do not drain before the next event is created.
    if next_event == "mouse-up":
        value.mouse_up(key="right")
    elif next_event == "key-up":
        value.send_key_up("f2")
    elif next_event == "key-down":
        value.send_key_down("w")
    elif next_event == "move":
        value.move(10, 10)
    else:
        value.scroll(-1, -1, 1)
    q.drain()
    assert q.flags == 0


@pytest.mark.parametrize("baseline", [0x10000 | 0x100000 | 0x8, 0x20000 | 0x4])
def test_unowned_modifiers_and_opposite_physical_side_are_preserved(queued_interaction, baseline):
    value, q = queued_interaction
    q.flags = baseline
    value.send_key_down("lshift")
    q.drain()
    value.mouse_down(key="right")
    q.drain()
    value.stop()
    q.drain()
    assert q.flags == baseline


def test_acknowledged_release_retires_override_before_new_physical_input(queued_interaction):
    value, q = queued_interaction
    value.send_key_down("shift")
    q.drain()
    value.send_key_up("shift")
    q.drain()
    value.move(10, 10)  # Observe both sources up, retiring the pending side.
    q.drain()
    q.flags = 0x20000 | 0x2  # A later independent physical left Shift.
    value.move(20, 20)
    q.drain()
    assert q.flags == 0x20000 | 0x2


def test_rapid_modifier_chord_uses_intended_state_before_native_drain(queued_interaction):
    value, q = queued_interaction
    value.send_key_down("shift")
    value.send_key_down("alt")
    q.drain()
    assert q.flags == 0x20000 | 0x2 | 0x80000 | 0x20
    value.stop()
    q.drain()
    assert q.flags == 0


def test_failed_modifier_release_is_not_reasserted_by_remaining_cleanup(queued_interaction):
    value, q = queued_interaction
    value.send_key_down("shift")
    value.mouse_down(key="right")
    q.drain()
    q.fail_up_once = 56
    before = len(q.posts)
    assert not value.release_all()
    q.drain()
    assert q.flags == 0
    assert value.held_state.snapshot().keys == ()
    assert value.held_state.snapshot().buttons == ()
    assert [event["kind"] for event in q.posts[before:]] == [q.kCGEventRightMouseUp]


def test_rejected_modifier_down_does_not_poison_sink_state(queued_interaction):
    value, q = queued_interaction
    value.event_sink._pre_post_check = lambda: (_ for _ in ()).throw(RuntimeError("denied"))
    with pytest.raises(RuntimeError, match="denied"):
        value.event_sink.key_event(56, True)
    assert value.event_sink._modifier_state == {}
    assert q.posts == []
