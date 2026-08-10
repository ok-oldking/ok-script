import unittest

from ok.ui.qt.events import QtEventDispatcher


class TestQtEventDispatcher(unittest.TestCase):
    def test_surplus_signal_arguments_are_discarded_for_parameterless_slot(self):
        dispatcher = QtEventDispatcher()
        calls = []

        dispatcher._invoke_callback(lambda: calls.append(True), (False,), {})

        self.assertEqual([True], calls)

    def test_slot_receives_the_positional_arguments_it_declares(self):
        dispatcher = QtEventDispatcher()
        calls = []

        dispatcher._invoke_callback(lambda first: calls.append(first), (1, 2, 3), {})

        self.assertEqual([1], calls)

    def test_variadic_subscriber_receives_every_argument(self):
        dispatcher = QtEventDispatcher()
        calls = []

        dispatcher._invoke_callback(lambda *args: calls.append(args), (1, 2, 3), {})

        self.assertEqual([(1, 2, 3)], calls)


if __name__ == "__main__":
    unittest.main()
