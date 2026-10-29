import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from qfluentwidgets import LineEdit

from ok.device.interaction_methods.keys import (
    is_mouse_button, get_mouse_button, XBUTTON1, XBUTTON2,
    WM_XBUTTONDOWN, WM_XBUTTONUP, MK_XBUTTON1, MK_XBUTTON2
)
from ok.device.interaction_methods.post_message import PostMessageInteraction
from ok.device.interaction_methods.pydirect import PyDirectInteraction
from ok.ui.qt.tasks.LabelAndLineEdit import LabelAndLineEdit, GlobalMouseButtonFilter
from ok.task.task import VALID_NAMED_KEYS, ExecutorOperation


class TestMouseButtons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_valid_named_keys_contains_mouse_buttons(self):
        for btn in ['mouse4', 'mouse5', 'xbutton1', 'xbutton2']:
            self.assertIn(btn, VALID_NAMED_KEYS)

    def test_executor_operation_validates_mouse_keys(self):
        op = ExecutorOperation(Mock(), Mock())
        self.assertEqual(op.validate_key('mouse4'), 'mouse4')
        self.assertEqual(op.validate_key('MOUSE5'), 'MOUSE5')
        self.assertEqual(op.validate_key('xbutton1'), 'xbutton1')

    def test_is_and_get_mouse_button(self):
        self.assertTrue(is_mouse_button('mouse4'))
        self.assertTrue(is_mouse_button('MOUSE5'))
        self.assertFalse(is_mouse_button('ctrl'))
        self.assertEqual(get_mouse_button('mouse4'), XBUTTON1)
        self.assertEqual(get_mouse_button('mouse5'), XBUTTON2)

    def test_post_message_interaction_dispatches_xbutton(self):
        capture = Mock()
        hwnd_window = Mock()
        hwnd_window.hwnd = 12345
        hwnd_window.top_hwnd = 12345
        interaction = PostMessageInteraction(capture, hwnd_window)
        interaction.post = Mock()
        interaction.try_activate = Mock()

        # Mouse 4 Down
        interaction.send_key_down('mouse4', activate=False)
        interaction.post.assert_called_once()
        args = interaction.post.call_args[0]
        self.assertEqual(args[0], WM_XBUTTONDOWN)

        # Mouse 5 Up
        interaction.post.reset_mock()
        interaction.send_key_up('mouse5')
        interaction.post.assert_called_once()
        args = interaction.post.call_args[0]
        self.assertEqual(args[0], WM_XBUTTONUP)

    @patch('ok.device.interaction_methods.pydirect.user32.mouse_event')
    def test_pydirect_interaction_dispatches_mouse_event(self, mock_mouse_event):
        capture = Mock()
        hwnd_window = Mock()
        hwnd_window.is_foreground = Mock(return_value=True)
        interaction = PyDirectInteraction(capture, hwnd_window)
        interaction.check_clickable = False

        interaction.send_key_down('mouse4')
        mock_mouse_event.assert_called_with(0x0080, 0, 0, XBUTTON1, 0)

        mock_mouse_event.reset_mock()
        interaction.send_key_up('mouse5')
        mock_mouse_event.assert_called_with(0x0100, 0, 0, XBUTTON2, 0)

    def test_global_mouse_button_filter_fills_hotkey(self):
        from ok import og
        orig_app = getattr(og, 'app', None)
        og.app = Mock(tr=lambda text: text)
        self.addCleanup(lambda: setattr(og, 'app', orig_app))

        config_desc = {'key': 'Test Key'}
        config = {'key': 't'}
        widget = LabelAndLineEdit(config_desc, config, 'key')
        widget.show()
        self.addCleanup(widget.close)

        line_edit = widget.line_edit
        line_edit.setFocus()
        QApplication.processEvents()
        self.assertEqual(QApplication.focusWidget(), line_edit)

        event_filter = GlobalMouseButtonFilter()
        press_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(10, 10),
            Qt.MouseButton.XButton1,
            Qt.MouseButton.XButton1,
            Qt.KeyboardModifier.NoModifier
        )

        consumed = event_filter.eventFilter(line_edit, press_event)
        self.assertTrue(consumed)
        self.assertEqual(line_edit.text(), 'mouse4')

        # Test mouse5 (XButton2)
        press_event_5 = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(10, 10),
            Qt.MouseButton.XButton2,
            Qt.MouseButton.XButton2,
            Qt.KeyboardModifier.NoModifier
        )
        consumed_5 = event_filter.eventFilter(line_edit, press_event_5)
        self.assertTrue(consumed_5)
        self.assertEqual(line_edit.text(), 'mouse5')


if __name__ == '__main__':
    unittest.main()
