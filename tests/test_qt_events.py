import unittest

from PySide6.QtCore import QObject
from shiboken6 import delete

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

    def test_callback_for_deleted_qobject_is_discarded(self):
        dispatcher = QtEventDispatcher()
        owner = QObject()
        callback = owner.objectName
        delete(owner)

        # Calling the bound method directly raises because its C++ object is
        # gone; queued application events must instead be harmlessly dropped.
        dispatcher._invoke_callback(callback, (), {})


if __name__ == "__main__":
    unittest.main()
