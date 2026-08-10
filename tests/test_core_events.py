import unittest

from ok.core.events import EventBus


class TestCoreEvents(unittest.TestCase):
    def test_named_and_catch_all_subscribers_receive_event(self):
        bus = EventBus()
        received = []
        all_events = []
        bus.task.connect(lambda task: received.append(task))
        bus.any.connect(all_events.append)

        bus.task.emit("demo")

        self.assertEqual(["demo"], received)
        self.assertEqual("task", all_events[0].name)
        self.assertEqual(("demo",), all_events[0].args)

    def test_disconnect_does_not_remove_catch_all_forwarding(self):
        bus = EventBus()
        all_events = []
        bus.any.connect(all_events.append)
        bus.task.connect(lambda _task: None)
        bus.task.disconnect()

        bus.task.emit("demo")

        self.assertEqual("task", all_events[0].name)


if __name__ == "__main__":
    unittest.main()
