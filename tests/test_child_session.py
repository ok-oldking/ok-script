import socket
import unittest
from unittest.mock import Mock, patch

import numpy as np

from ok.child_session import host, protocol
from ok.device.DeviceManager import DeviceManager


class FakeClient:
    """Records agent calls and returns canned replies."""

    def __init__(self, replies=None):
        self.calls = []
        self.replies = replies or {}

    def call(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        return self.replies.get(cmd, {'ok': True})


class TestProtocol(unittest.TestCase):
    def test_message_with_payload_round_trips(self):
        left, right = socket.socketpair()
        try:
            payload = np.arange(24, dtype=np.uint8).tobytes()
            protocol.send_message(left, {'ok': True, 'w': 4, 'h': 2}, payload)
            message, received = protocol.read_message(right.makefile('rb'))
            self.assertEqual(len(payload), message['len'])
            self.assertEqual(payload, received)
            self.assertEqual(4, message['w'])
        finally:
            left.close()
            right.close()

    def test_message_without_payload(self):
        left, right = socket.socketpair()
        try:
            protocol.send_message(left, {'cmd': 'ping'})
            message, payload = protocol.read_message(right.makefile('rb'))
            self.assertEqual({'cmd': 'ping'}, message)
            self.assertEqual(b'', payload)
        finally:
            left.close()
            right.close()

    def test_project_key_is_stable_and_case_insensitive(self):
        self.assertEqual(protocol.project_key(r'C:\Games\Project'), protocol.project_key(r'c:\games\project'))
        self.assertNotEqual(protocol.project_key(r'C:\Games\A'), protocol.project_key(r'C:\Games\B'))


class TestHost(unittest.TestCase):
    def test_window_spec_normalizes_exe(self):
        spec = host.window_spec({'exe': 'Game.exe', 'hwnd_class': 'UnrealWindow', 'title': None})
        self.assertEqual({'exe': ['Game.exe'], 'hwnd_class': 'UnrealWindow', 'title': None}, spec)

    def test_window_spec_ignores_regex_title(self):
        import re
        spec = host.window_spec({'exe': ['a.exe'], 'title': re.compile('x')})
        self.assertIsNone(spec['title'])

    def test_autostart_command_runs_agent_for_project(self):
        command = host.autostart_command(r'E:\proj')
        self.assertIn('agent.py', command)
        self.assertIn(r'--project "E:\proj"', command)
        self.assertTrue(host.autostart_name(r'E:\proj').startswith('ok-script-child-session-'))

    def test_autostart_is_current_only_for_this_command(self):
        command = host.autostart_command(r'E:\proj')
        with patch.object(host, 'autostart_value', return_value=command):
            self.assertTrue(host.is_autostart_installed(r'E:\proj'))
        with patch.object(host, 'autostart_value', return_value='"old.exe" agent.py'):
            self.assertFalse(host.is_autostart_installed(r'E:\proj'))
        with patch.object(host, 'autostart_value', return_value=None):
            self.assertFalse(host.is_autostart_installed(r'E:\proj'))

    def test_shortcut_lives_in_startup_folder(self):
        with patch.object(host, 'startup_folder', return_value=r'C:\Startup'):
            path = host.shortcut_path(r'E:\proj')
        self.assertTrue(path.startswith('C:\\Startup\\ok-script-child-session-'))
        self.assertTrue(path.endswith('.lnk'))

    def test_write_agent_config_drops_empty_names(self):
        with patch.object(protocol, 'write_json') as write:
            data = host.write_agent_config(r'E:\proj', {'exe': 'g.exe'}, ['QQ.exe', ' ', ''], elevate=False)
        self.assertEqual(['QQ.exe'], data['close_apps'])
        self.assertFalse(data['elevate'])
        write.assert_called_once()


class TestChildSessionInteraction(unittest.TestCase):
    def make(self):
        from ok.device.interaction_methods.child_session import ChildSessionInteraction
        client = FakeClient()
        return ChildSessionInteraction(Mock(), client=client), client

    def test_client_comes_from_child_session_capture(self):
        from ok.device.interaction_methods.child_session import ChildSessionInteraction
        capture = Mock()
        capture.client = FakeClient()
        interaction = ChildSessionInteraction(capture, Mock())
        interaction.move(5, 6)
        self.assertEqual(('move', {'x': 5, 'y': 6}), capture.client.calls[-1])

    def test_click_is_forwarded_with_client_coordinates(self):
        interaction, client = self.make()
        interaction.click(100.6, 200.2, key='right', down_time=0.1)
        self.assertEqual(('click', {'x': 100, 'y': 200, 'key': 'right', 'down_time': 0.1}), client.calls[-1])

    def test_swipe_converts_milliseconds_to_seconds(self):
        interaction, client = self.make()
        interaction.swipe(1, 2, 3, 4, 500, settle_time=0.2)
        cmd, kwargs = client.calls[-1]
        self.assertEqual('swipe', cmd)
        self.assertAlmostEqual(0.5, kwargs['duration'])
        self.assertAlmostEqual(0.2, kwargs['settle_time'])

    def test_keys_are_forwarded(self):
        interaction, client = self.make()
        interaction.send_key_down('lshift')
        interaction.send_key_up('lshift')
        interaction.back()
        self.assertEqual(['key_down', 'key_up', 'send_key'], [cmd for cmd, _ in client.calls])
        self.assertEqual('esc', client.calls[-1][1]['key'])

    def test_agent_error_does_not_raise_into_tasks(self):
        from ok.child_session.protocol import AgentError
        interaction, client = self.make()
        client.call = Mock(side_effect=AgentError('not running'))
        interaction.click(1, 2)


class TestChildSessionWindow(unittest.TestCase):
    def test_host_handle_is_zero_and_state_comes_from_agent(self):
        from ok.device.capture_methods.child_session import ChildSessionWindow
        client = FakeClient({'window_info': {'exists': True, 'hwnd': 1234, 'width': 1920, 'height': 1080,
                                             'title': 'Game', 'foreground': True}})
        window = ChildSessionWindow(client, Mock())
        self.assertEqual(0, window.hwnd)
        self.assertTrue(window.exists)
        self.assertEqual((1920, 1080), (window.width, window.height))
        self.assertEqual('Game', window.hwnd_title)
        self.assertTrue(window.is_child_session)

    def test_unreachable_agent_means_no_window(self):
        from ok.child_session.protocol import AgentError
        from ok.device.capture_methods.child_session import ChildSessionWindow
        client = Mock()
        client.call.side_effect = AgentError('not running')
        window = ChildSessionWindow(client, Mock())
        self.assertFalse(window.exists)
        self.assertEqual(0, window.width)


class TestDeviceManagerChildSession(unittest.TestCase):
    def make_manager(self, child=True):
        manager = DeviceManager.__new__(DeviceManager)
        manager.windows_capture_config = {'exe': ['Game.exe'], 'capture_method': ['WGC', 'BitBlt'],
                                          'interaction': ['PostMessage', 'Pynput']}
        manager.child_session_config = {'resolution': (1920, 1080)} if child else None
        manager.capture_method = None
        manager.interaction = None
        manager.device_dict = {}
        manager.config = {'capture': 'WGC', 'interaction': 'PostMessage', 'preferred': 'pc'}
        manager.start = Mock()
        return manager

    def test_child_session_is_a_pc_capture_and_interaction(self):
        manager = self.make_manager()
        device = {'device': 'windows'}
        self.assertEqual(['WGC', 'BitBlt', 'ChildSession'], DeviceManager.available_capture_methods(manager, device))
        self.assertEqual(['PostMessage', 'Pynput', 'ChildSession'],
                         DeviceManager.available_interaction_methods(manager, device))

    def test_not_offered_without_config(self):
        manager = self.make_manager(child=False)
        device = {'device': 'windows'}
        self.assertNotIn('ChildSession', DeviceManager.available_capture_methods(manager, device))
        self.assertNotIn('ChildSession', DeviceManager.available_interaction_methods(manager, device))

    def test_selecting_child_session_capture_pairs_the_interaction(self):
        from ok.device.interaction_methods.child_session import ChildSessionInteraction
        manager = self.make_manager()
        manager.set_capture('ChildSession')
        self.assertEqual('ChildSession', manager.config['interaction'])
        self.assertIs(ChildSessionInteraction, manager.win_interaction_class)
        manager.set_capture('WGC')
        self.assertEqual('PostMessage', manager.config['interaction'])

    def test_uses_child_session(self):
        manager = self.make_manager()
        manager.device_dict = {'pc': {'device': 'windows'}}
        self.assertFalse(manager.uses_child_session())
        manager.config['capture'] = 'ChildSession'
        self.assertTrue(manager.uses_child_session())

    def test_child_session_capture_swaps_window_tracker(self):
        from ok.device.capture_methods.child_session import ChildSessionCaptureMethod, ChildSessionWindow
        manager = self.make_manager()
        pc_window = Mock()
        manager.hwnd_window = pc_window
        manager.exit_event = Mock()
        manager._pc_hwnd_window = None
        manager._child_session_client = FakeClient()
        manager.config['capture'] = 'ChildSession'
        manager.use_windows_capture()
        self.assertIsInstance(manager.capture_method, ChildSessionCaptureMethod)
        self.assertIsInstance(manager.hwnd_window, ChildSessionWindow)
        manager._leave_child_session()
        self.assertIs(pc_window, manager.hwnd_window)


class TestPcDeviceStatus(unittest.TestCase):
    def test_pc_device_reports_the_child_session_window(self):
        from ok.device.capture_methods.child_session import ChildSessionCaptureMethod, ChildSessionWindow
        manager = TestDeviceManagerChildSession().make_manager()
        manager.config['capture'] = 'ChildSession'
        client = FakeClient({'window_info': {'exists': True, 'width': 1920, 'height': 1080}})
        manager.capture_method = ChildSessionCaptureMethod(client, ChildSessionWindow(client, Mock()), Mock())
        device = {'connected': False, 'width': 0, 'height': 0}
        manager._report_child_session_window(device)
        self.assertTrue(device['connected'])
        self.assertEqual('1920x1080', device['resolution'])

    def test_other_captures_keep_the_host_state(self):
        manager = TestDeviceManagerChildSession().make_manager()
        device = {'connected': False}
        manager._report_child_session_window(device)
        self.assertEqual({'connected': False}, device)


class TestSessionLifetime(unittest.TestCase):
    def test_close_signs_out_the_child_session(self):
        manager = TestDeviceManagerChildSession().make_manager()
        manager.hwnd_window = None
        with patch('ok.child_session.win_api.child_session_id', return_value=16), \
                patch('ok.child_session.win_api.logoff', return_value=True) as logoff:
            manager.close()
        logoff.assert_called_once_with(16, wait=False)

    def test_close_leaves_sessions_alone_without_config(self):
        manager = TestDeviceManagerChildSession().make_manager(child=False)
        manager.hwnd_window = None
        with patch('ok.child_session.win_api.child_session_id', return_value=16), \
                patch('ok.child_session.win_api.logoff') as logoff:
            manager.close()
        logoff.assert_not_called()


class TestOwnAudioMute(unittest.TestCase):
    def _session(self, pid, muted):
        volume = Mock()
        volume.GetMute.return_value = muted
        session = Mock()
        session.Process.pid = pid
        session._ctl.QueryInterface.return_value = volume
        return session, volume

    def test_corrects_only_this_process_and_only_when_different(self):
        import os
        from ok.ui.qt.child_session.child_session_tab import _ensure_own_audio_muted
        own_wrong, own_wrong_volume = self._session(os.getpid(), 1)
        own_right, own_right_volume = self._session(os.getpid(), 0)
        other, other_volume = self._session(os.getpid() + 1, 1)
        with patch('pycaw.utils.AudioUtilities.GetAllSessions', return_value=[own_wrong, own_right, other]):
            _ensure_own_audio_muted(False)
        own_wrong_volume.SetMute.assert_called_once_with(False, None)
        own_right_volume.SetMute.assert_not_called()
        other_volume.SetMute.assert_not_called()


class TestAspectView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_view_keeps_ratio_and_is_centered(self):
        from PySide6.QtWidgets import QWidget
        from ok.ui.qt.child_session.child_session_tab import AspectView
        inner = QWidget()
        box = AspectView(inner, 1920, 1080)
        box.resize(1000, 1000)
        box.resizeEvent(None)
        self.assertEqual((1000, 562), (inner.width(), inner.height()))
        self.assertEqual(219, inner.y())
        box.resize(2000, 500)
        box.resizeEvent(None)
        self.assertEqual((889, 500), (inner.width(), inner.height()))
        self.assertEqual(555, inner.x())


class TestConnectionLabels(unittest.TestCase):
    def test_child_session_listed_for_pc_window(self):
        from ok.ui.qt.shell import connection
        manager = TestDeviceManagerChildSession().make_manager()
        manager.get_preferred_capture = lambda: 'ChildSession'
        device = {'device': 'windows'}
        options, index, names = connection.capture_options(manager, device)
        self.assertEqual(['WGC', 'BitBlt', 'ChildSession'], names)
        self.assertEqual(2, index)
        options, index, names = connection.interaction_options(manager, device)
        self.assertIn('ChildSession', names)


if __name__ == '__main__':
    unittest.main()
