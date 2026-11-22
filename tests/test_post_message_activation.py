import unittest
from unittest.mock import Mock, patch

import win32con

from ok.device.interaction_methods.post_message import PostMessageInteraction


class TestPostMessageActivation(unittest.TestCase):

    def setUp(self):
        self.hwnd_window = Mock()
        self.hwnd_window.hwnd = 100
        self.hwnd_window.top_hwnd = 100
        self.hwnd_window.visible_monitors = []
        self.interaction = PostMessageInteraction(Mock(), self.hwnd_window)
        self.interaction.post = Mock()

    def activations(self):
        return [c for c in self.interaction.post.call_args_list if c.args[0] == win32con.WM_ACTIVATE]

    def test_registers_visibility_monitor(self):
        self.assertIn(self.interaction, self.hwnd_window.visible_monitors)

    def test_activates_once_until_visibility_changes(self):
        self.interaction.send_key('a')
        self.interaction.send_key('b')
        self.interaction.input_text('xy')
        self.assertEqual(len(self.activations()), 1)

        self.interaction.on_visible(False)
        self.interaction.send_key('a')
        self.assertEqual(len(self.activations()), 2)

    def test_reactivates_when_target_hwnd_changes(self):
        self.interaction.try_activate()
        with patch('ok.device.interaction_methods.post_message.win32gui.IsWindow', return_value=True):
            self.interaction._dynamic_target_hwnd = 200
            self.interaction.try_activate()
            self.interaction.try_activate()
        targets = [c.kwargs['hwnd'] for c in self.activations()]
        self.assertEqual(targets, [100, 100, 200])

    def test_force_activation(self):
        self.interaction.try_activate()
        self.interaction.try_activate(force=True)
        self.assertEqual(len(self.activations()), 2)

    def test_activate_false_skips_activation(self):
        self.interaction.send_key_down('a', activate=False)
        self.interaction.input_text('x', activate=False)
        self.assertEqual(self.activations(), [])


if __name__ == '__main__':
    unittest.main()
