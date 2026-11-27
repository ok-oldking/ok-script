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


class TestRdpViewOverlayClipping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _make_host(self, top_margin=80):
        from contextlib import ExitStack
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
        from ok.ui.qt.child_session.rdp_view import RdpView

        stack = ExitStack()
        stack.enter_context(patch('ok.ui.qt.child_session.rdp_view.RdpView._win32_move'))
        stack.enter_context(patch('ok.ui.qt.child_session.rdp_view.RdpView._win32_show'))
        stack.enter_context(patch('ok.ui.qt.child_session.rdp_view.RdpView._win32_set_parent'))
        stack.enter_context(patch('ok.ui.qt.child_session.rdp_view.RdpView._win32_clear_region', return_value=True))
        stack.enter_context(patch('ok.ui.qt.child_session.rdp_view.RdpView._win32_set_region', return_value=True))

        window = QWidget()
        window.resize(900, 600)
        container = QWidget(window)
        outer = QVBoxLayout(window)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(100, top_margin, 40, 40)
        view = RdpView(container)
        layout.addWidget(view)
        window.show()
        QApplication.processEvents()

        def cleanup():
            view._hwnd = None
            view.dispose()
            window.close()
            window.deleteLater()
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            stack.close()

        self.addCleanup(cleanup)
        return window, container, view

    def _activate(self, window, view):
        view._hwnd = 1
        view._parent_hwnd = int(window.winId())
        view._session_active = True
        view._sync_native_window()

    def _stub_rdp_backend(self, hwnd=98765):
        import ctypes
        from contextlib import ExitStack
        from types import SimpleNamespace
        import comtypes.client

        user32 = Mock()
        user32.CreateWindowExW.return_value = hwnd
        user32.SetWindowRgn.return_value = 1
        atl = Mock()
        atl.AtlAxGetControl.return_value = 0

        rdp = SimpleNamespace(
            Version='10.0',
            AdvancedSettings9=SimpleNamespace(),
            SecuredSettings3=SimpleNamespace(),
            Connect=Mock(),
            Disconnect=Mock(),
        )
        extended = SimpleNamespace(Property={})
        rdp.QueryInterface = Mock(return_value=extended)
        mstsc = SimpleNamespace(IMsRdpClient9=object(), IMsTscAxEvents=object(), IMsRdpExtendedSettings=object())

        class FakeUnknown(ctypes.c_void_p):
            def QueryInterface(self, _iface):
                return rdp

        stack = ExitStack()
        stack.enter_context(patch('ok.ui.qt.child_session.rdp_view._user32', return_value=user32))
        # ctypes.WinDLL is patched below; keep _gdi32() from caching that mock.
        stack.enter_context(patch('ok.ui.qt.child_session.rdp_view._gdi32', return_value=Mock()))
        stack.enter_context(patch('ok.ui.qt.child_session.rdp_view._mstsc', return_value=mstsc))
        stack.enter_context(patch('ctypes.WinDLL', return_value=atl))
        stack.enter_context(patch('comtypes.client.GetEvents', return_value=Mock()))
        stack.enter_context(patch('ctypes.POINTER', return_value=FakeUnknown))
        return stack, user32, rdp

    def test_view_and_ancestors_stay_alien_and_native_hides_on_tab_switch_or_disconnect(self):
        from PySide6.QtCore import Qt
        window, container, view = self._make_host()
        self.assertFalse(view.testAttribute(Qt.WidgetAttribute.WA_NativeWindow))
        self.assertFalse(container.testAttribute(Qt.WidgetAttribute.WA_NativeWindow))
        self.assertFalse(view._native_visible)
        self.assertFalse(view._filter_installed)

        self._activate(window, view)
        self.assertTrue(view._native_visible)
        self.assertTrue(view._filter_installed)
        self.assertFalse(view.testAttribute(Qt.WidgetAttribute.WA_NativeWindow))
        self.assertFalse(container.testAttribute(Qt.WidgetAttribute.WA_NativeWindow))

        view.hide()
        self.assertFalse(view._native_visible)
        view.show()
        self.assertTrue(view._native_visible)

        view._on_disconnected(0)
        self.assertFalse(view._native_visible)
        self.assertFalse(view._filter_installed)
        self._activate(window, view)
        self.assertTrue(view._native_visible)
        self.assertTrue(view._filter_installed)
        view.disconnect_session()
        self.assertFalse(view._native_visible)
        self.assertFalse(view._filter_installed)

    def test_connect_session_creates_control_under_top_level_window_keeping_view_alien(self):
        from PySide6.QtCore import Qt

        window, container, view = self._make_host()
        stack, user32, rdp = self._stub_rdp_backend()
        with stack:
            view.connect_session(1920, 1080, 'user', 'pass')

        self.assertEqual(int(window.winId()), user32.CreateWindowExW.call_args.args[8])
        rdp.Connect.assert_called_once()
        self.assertTrue(view._native_visible)
        self.assertTrue(view._filter_installed)
        self.assertFalse(view.testAttribute(Qt.WidgetAttribute.WA_NativeWindow))
        self.assertFalse(container.testAttribute(Qt.WidgetAttribute.WA_NativeWindow))

    def test_hidden_connect_does_not_install_app_filter_until_shown(self):
        window, _container, view = self._make_host()
        view.hide()
        stack, _user32, rdp = self._stub_rdp_backend()
        with stack:
            view.connect_session(1920, 1080, 'user', 'pass')

        rdp.Connect.assert_called_once()
        self.assertFalse(view._native_visible)
        self.assertFalse(view._filter_installed)

        view.show()
        self.assertTrue(view._native_visible)
        self.assertTrue(view._filter_installed)

        view.hide()
        self.assertFalse(view._native_visible)
        self.assertFalse(view._filter_installed)

    def test_win32_set_region_rolls_back_on_partial_gdi_failure(self):
        from unittest.mock import call
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QRegion
        from PySide6.QtWidgets import QApplication, QWidget
        from ok.ui.qt.child_session.rdp_view import RdpView
        from ok.ui.qt.kit.popover import Popover

        orig_set_region = RdpView._win32_set_region
        window, _container, view = self._make_host()
        anchor = QWidget(window)
        anchor.setGeometry(20, 20, 80, 30)
        anchor.show()
        popover = Popover(window)
        popover.setFixedSize(360, 400)
        self._activate(window, view)
        QApplication.processEvents()

        gdi32 = Mock()
        gdi32.CreateRectRgn.side_effect = [101, 201, 0]
        gdi32.CombineRgn.return_value = 2
        user32 = Mock()
        with patch.object(view, '_win32_set_region', lambda vis, ratio: orig_set_region(view, vis, ratio)), \
                patch('ok.ui.qt.child_session.rdp_view._gdi32', return_value=gdi32), \
                patch('ok.ui.qt.child_session.rdp_view._user32', return_value=user32):
            popover.popup(anchor, above=False)
            QApplication.processEvents()
            self.assertIsNone(view._applied_region)
            self.assertFalse(view._native_visible)
            user32.SetWindowRgn.assert_not_called()
            self.assertEqual([call(201), call(101)], gdi32.DeleteObject.call_args_list)

            gdi32.reset_mock()
            gdi32.CreateRectRgn.side_effect = [102, 202]
            gdi32.CombineRgn.return_value = 0
            two_rects = QRegion(QRect(0, 0, 100, 40)) + QRegion(QRect(0, 60, 100, 40))
            self.assertFalse(view._apply_native_region(two_rects))
            self.assertIsNone(view._applied_region)
            user32.SetWindowRgn.assert_not_called()
            self.assertEqual([call(202), call(102)], gdi32.DeleteObject.call_args_list)

    def test_region_apply_and_clear_failures_are_safe_and_retried(self):
        from PySide6.QtWidgets import QApplication, QWidget
        from ok.ui.qt.kit.popover import Popover

        window, _container, view = self._make_host()
        anchor = QWidget(window)
        anchor.setGeometry(20, 20, 80, 30)
        anchor.show()
        popover = Popover(window)
        popover.setFixedSize(360, 400)
        self._activate(window, view)
        QApplication.processEvents()

        with patch.object(view, '_win32_set_region', return_value=False):
            popover.popup(anchor, above=False)
            QApplication.processEvents()
            self.assertIsNone(view._applied_region)
            self.assertFalse(view._native_visible)

        view._sync_native_window()
        self.assertIsNotNone(view._applied_region)
        self.assertTrue(view._native_visible)

        with patch.object(view, '_win32_clear_region', return_value=False):
            popover.close_popover()
            QApplication.processEvents()
            self.assertIsNotNone(view._applied_region)

        view._sync_native_window()
        self.assertIsNone(view._applied_region)

    def test_popover_clips_overlapped_region_and_restores_on_close(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QApplication, QWidget
        from ok.ui.qt.kit.popover import Popover
        window, _container, view = self._make_host()
        anchor = QWidget(window)
        anchor.setGeometry(20, 20, 80, 30)
        anchor.show()
        popover = Popover(window)
        popover.setFixedSize(360, 400)
        self._activate(window, view)
        QApplication.processEvents()

        popover.popup(anchor, above=False)
        QApplication.processEvents()
        self.assertTrue(view._native_visible)
        region = view._applied_region
        self.assertIsNotNone(region)
        self.assertFalse(region.isEmpty())
        self.assertFalse(region.contains(QPoint(10, 10)))
        self.assertTrue(region.contains(QPoint(view.width() - 10, view.height() - 10)))

        popover.close_popover()
        QApplication.processEvents()
        self.assertTrue(view._native_visible)
        self.assertIsNone(view._applied_region)

    def test_dialog_hides_native_completely_and_restores_on_reject(self):
        from PySide6.QtWidgets import QApplication
        from ok.ui.qt.kit.dialogs import Dialog
        window, _container, view = self._make_host(top_margin=20)
        self._activate(window, view)
        dialog = Dialog(window, 'Sign in', 'Enter password')
        QApplication.processEvents()
        self.assertTrue(view._native_visible)

        dialog.open()
        QApplication.processEvents()
        self.assertFalse(view._native_visible)
        self.assertIsNone(view._applied_region)

        dialog.reject()
        QApplication.processEvents()
        self.assertTrue(view._native_visible)
        self.assertIsNone(view._applied_region)
        dialog.deleteLater()

    def test_toast_masks_overlapped_region_and_restores_on_close(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QApplication
        from ok.ui.qt.kit.feedback import show_toast
        window, _container, view = self._make_host(top_margin=20)
        self._activate(window, view)
        toast = show_toast(window, 'Child session warning message', duration=0)
        QApplication.processEvents()
        toast_in_view = view.mapFrom(window, toast.geometry().center())
        self.assertTrue(view.rect().contains(toast_in_view))
        self.assertTrue(view._native_visible)
        region = view._applied_region
        self.assertIsNotNone(region)
        self.assertFalse(region.isEmpty())
        self.assertFalse(region.contains(toast_in_view))
        self.assertTrue(region.contains(QPoint(view.width() - 10, view.height() - 10)))

        toast.close()
        QApplication.processEvents()
        self.assertTrue(view._native_visible)
        self.assertIsNone(view._applied_region)

    def test_native_region_is_clipped_to_ancestor_bounds(self):
        from PySide6.QtCore import QEvent, QRect
        from PySide6.QtGui import QRegion
        from PySide6.QtWidgets import QApplication, QWidget
        from ok.ui.qt.child_session.rdp_view import RdpView

        with patch('ok.ui.qt.child_session.rdp_view.RdpView._win32_move'), \
                patch('ok.ui.qt.child_session.rdp_view.RdpView._win32_show'), \
                patch('ok.ui.qt.child_session.rdp_view.RdpView._win32_set_parent'), \
                patch('ok.ui.qt.child_session.rdp_view.RdpView._win32_clear_region', return_value=True), \
                patch('ok.ui.qt.child_session.rdp_view.RdpView._win32_set_region', return_value=True):
            window = QWidget()
            window.resize(900, 600)
            container = QWidget(window)
            container.setGeometry(50, 50, 200, 100)
            view = RdpView(container)
            view.setGeometry(0, 0, 400, 300)  # overflows its container, as at minimum size
            window.show()
            QApplication.processEvents()
            try:
                self._activate(window, view)
                self.assertTrue(view._native_visible)
                self.assertEqual(QRegion(QRect(0, 0, 200, 100)), view._applied_region)

                container.setGeometry(50, 50, 500, 400)
                QApplication.processEvents()
                view._sync_native_window()
                self.assertIsNone(view._applied_region)
            finally:
                view._hwnd = None
                view.dispose()
                window.close()
                window.deleteLater()
                QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_reconnect_without_connect_call_shows_native_again(self):
        window, _container, view = self._make_host()
        self._activate(window, view)
        view._on_disconnected(3)
        self.assertFalse(view._native_visible)
        view.connected.emit()
        self.assertTrue(view.is_connected)
        self.assertTrue(view._native_visible)

    def test_failed_control_setup_destroys_window_and_allows_retry(self):
        window, _container, view = self._make_host()
        stack, user32, _rdp = self._stub_rdp_backend()
        with stack, patch('comtypes.client.GetEvents', side_effect=OSError('no events')):
            with self.assertRaises(OSError):
                view.connect_session(1920, 1080, 'user', 'pass')
            user32.DestroyWindow.assert_called_once()
            self.assertIsNone(view._hwnd)
            self.assertIsNone(view._rdp)

    def test_start_session_ignored_until_mounted(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        from ok.ui.qt.child_session.child_session_tab import ChildSessionTab

        dm = Mock()
        dm.get_preferred_device.return_value = None
        dm.child_session_client.return_value.try_call.return_value = None
        with patch('ok.child_session.host.settings', return_value={}), \
                patch('ok.child_session.host.sync_agent_config'), \
                patch('ok.child_session.host.install_autostart') as install, \
                patch('ok.child_session.win_api.is_enabled', return_value=True), \
                patch('ok.child_session.win_api.child_session_id', return_value=None), \
                patch('ok.child_session.credentials.load', return_value=('user', 'pass')), \
                patch('ok.ui.qt.child_session.child_session_tab._ensure_own_audio_muted'), \
                patch('ok.ui.qt.child_session.child_session_tab.ChildSessionTab.refresh'):
            tab = ChildSessionTab({'child_session': {'resolution': (1920, 1080)}, 'windows': {'exe': 'g.exe'}}, dm)
            try:
                tab.start_session()
                install.assert_not_called()
                self.assertFalse(tab._starting)
            finally:
                tab.dispose()
                tab.deleteLater()
                QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_audio_mutes_when_window_inactive_and_background_mute_on(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
        from ok.ui.qt.child_session.child_session_tab import ChildSessionTab

        dm = Mock()
        dm.get_preferred_device.return_value = None
        dm.child_session_client.return_value.try_call.return_value = None
        with patch('ok.child_session.host.settings', return_value={}), \
                patch('ok.child_session.host.sync_agent_config'), \
                patch('ok.child_session.win_api.is_enabled', return_value=True), \
                patch('ok.ui.qt.child_session.child_session_tab._ensure_own_audio_muted'), \
                patch('ok.ui.qt.child_session.child_session_tab.ChildSessionTab.refresh'):
            window = QWidget()
            layout = QVBoxLayout(window)
            tab = ChildSessionTab({'child_session': {'resolution': (1920, 1080)}, 'windows': {'exe': 'g.exe'}}, dm)
            layout.addWidget(tab)
            try:
                window.show()
                QApplication.processEvents()
                tab.view.is_connected = True
                with patch.object(window, 'isActiveWindow', return_value=False):
                    with patch('ok.ui.qt.child_session.child_session_tab._mute_in_background', return_value=True):
                        self.assertFalse(tab._audible())
                    with patch('ok.ui.qt.child_session.child_session_tab._mute_in_background', return_value=False):
                        self.assertTrue(tab._audible())
                with patch.object(window, 'isActiveWindow', return_value=True), \
                        patch('ok.ui.qt.child_session.child_session_tab._mute_in_background', return_value=True):
                    self.assertTrue(tab._audible())
            finally:
                tab.view.is_connected = False
                tab.dispose()
                window.close()
                window.deleteLater()
                QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_animated_stacked_widget_skips_transition_for_opt_out_page(self):
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QWidget
        from ok.ui.qt.kit.motion import AnimatedStackedWidget
        stack = AnimatedStackedWidget(Qt.Orientation.Vertical)
        stack.resize(400, 300)
        normal = QWidget()
        native_page = QWidget()
        native_page.setProperty('skip_transition', True)
        stack.addWidget(normal)
        stack.addWidget(native_page)
        stack.show()
        QApplication.processEvents()

        def cleanup():
            stack.close()
            stack.deleteLater()
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

        self.addCleanup(cleanup)

        stack.setCurrentWidget(native_page)
        self.assertIsNone(native_page.graphicsEffect())
        self.assertFalse(stack.is_animating())

        stack.setCurrentWidget(normal)
        self.assertIsInstance(normal.graphicsEffect(), QGraphicsOpacityEffect)
        self.assertTrue(stack.is_animating())

    def test_child_session_tab_settings_button_and_switch_stay_intact_and_clickable(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
        from ok.ui.qt.child_session.child_session_tab import ChildSessionTab
        from ok.ui.qt.kit.buttons import Button
        from ok.ui.qt.kit.navigation import NavItem
        from ok.ui.qt.kit.switch import Switch

        dm = Mock()
        dm.get_preferred_device.return_value = None
        dm.child_session_client.return_value.try_call.return_value = None

        with patch('ok.child_session.host.settings', return_value={}), \
                patch('ok.child_session.host.sync_agent_config'), \
                patch('ok.child_session.host.install_autostart'), \
                patch('ok.child_session.win_api.is_enabled', return_value=True), \
                patch('ok.child_session.win_api.child_session_id', return_value=None), \
                patch('ok.child_session.credentials.load', return_value=None), \
                patch('ok.child_session.credentials.forget'), \
                patch('ok.ui.qt.child_session.child_session_tab._ensure_own_audio_muted'), \
                patch('ok.ui.qt.child_session.child_session_tab.ChildSessionTab.refresh'):
            window = QWidget()
            window.resize(900, 700)
            layout = QVBoxLayout(window)
            tab = ChildSessionTab({'child_session': {'resolution': (1920, 1080)}, 'windows': {'exe': 'g.exe'}}, dm)
            nav_settings = NavItem('settings', 'Settings', 'gear', window)
            layout.addWidget(tab)
            layout.addWidget(nav_settings)
            try:
                window.show()
                QApplication.processEvents()

                self.assertIn(tab.settings_button, tab.children())
                self.assertIn(tab.view_only_switch, tab.children())
                self.assertIs(Button, type(tab.settings_button))
                self.assertIs(Switch, type(tab.view_only_switch))
                self.assertFalse(tab.settings_group.isVisible())

                tab.settings_button.click()
                QApplication.processEvents()
                self.assertTrue(tab.settings_group.isVisible())

                tab.settings_button.click()
                QApplication.processEvents()
                self.assertFalse(tab.settings_group.isVisible())

                late_button = Button('Late', 'gear', 'subtle', size='small', parent=window)
                late_nav = NavItem('late_nav', 'Late Nav', 'gear', window)
                QApplication.processEvents()
                self.assertIn(late_button, window.children())
                self.assertIn(late_nav, window.children())
                self.assertIs(Button, type(late_button))
                self.assertIs(NavItem, type(late_nav))

                clicks = []
                late_button.clicked.connect(lambda: clicks.append('button'))
                late_nav.clicked.connect(lambda: clicks.append('nav'))
                late_button.click()
                late_nav.click()
                self.assertEqual(['button', 'nav'], clicks)

                # Failed saved-password sign-ins replace the previous toast instead of stacking.
                tab._starting = True
                tab._used_saved_password = True
                tab._on_disconnected(1)
                first_toast = tab._error_toast
                self.assertIsNotNone(first_toast)
                self.assertTrue(first_toast.isVisible())

                tab._starting = True
                tab._used_saved_password = True
                tab._on_disconnected(1)
                second_toast = tab._error_toast
                self.assertIsNot(first_toast, second_toast)
                self.assertFalse(first_toast.isVisible())
                self.assertTrue(second_toast.isVisible())

                tab.forget_password()
                self.assertIsNone(tab._error_toast)
                self.assertFalse(second_toast.isVisible())

                # Re-entrant start_session calls while the password dialog is open are ignored.
                calls = []

                def fake_ask():
                    calls.append(True)
                    tab.start_session()
                    return None

                with patch.object(tab, '_ask_password', side_effect=fake_ask):
                    tab.start_session()
                self.assertEqual([True], calls)
            finally:
                tab.dispose()
                window.close()
                window.deleteLater()
                QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_auto_start_waits_for_mount_and_keeps_tab_alien(self):
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget
        from ok.ui.qt.child_session.child_session_tab import ChildSessionTab

        dm = Mock()
        dm.get_preferred_device.return_value = object()
        dm.uses_child_session.return_value = True
        dm.child_session_client.return_value.try_call.return_value = None

        rdp_stack, user32, rdp = self._stub_rdp_backend()
        with rdp_stack, \
                patch('ok.child_session.host.settings', return_value={'auto_connect': True}), \
                patch('ok.child_session.host.sync_agent_config'), \
                patch('ok.child_session.host.install_autostart'), \
                patch('ok.child_session.win_api.is_enabled', return_value=True), \
                patch('ok.child_session.win_api.child_session_id', return_value=None), \
                patch('ok.child_session.credentials.load', return_value=('user', 'pass')), \
                patch('ok.ui.qt.child_session.child_session_tab._ensure_own_audio_muted'), \
                patch('ok.ui.qt.child_session.child_session_tab.ChildSessionTab._collect_status'):
            tab = ChildSessionTab({'child_session': {'resolution': (1920, 1080)}, 'windows': {'exe': 'g.exe'}}, dm)
            window = QWidget()
            try:
                user32.CreateWindowExW.assert_not_called()
                self.assertFalse(tab._auto_start_checked)
                self.assertFalse(tab.testAttribute(Qt.WidgetAttribute.WA_NativeWindow))
                self.assertFalse(tab.view.testAttribute(Qt.WidgetAttribute.WA_NativeWindow))

                window.resize(900, 700)
                layout = QVBoxLayout(window)
                pages = QStackedWidget(window)
                pages.addWidget(QWidget())
                pages.addWidget(tab)
                layout.addWidget(pages)
                window.show()
                QApplication.processEvents()

                user32.CreateWindowExW.assert_called_once()
                self.assertEqual(int(window.winId()), user32.CreateWindowExW.call_args.args[8])
                rdp.Connect.assert_called_once()
                self.assertFalse(tab.testAttribute(Qt.WidgetAttribute.WA_NativeWindow))
                self.assertFalse(tab.view.testAttribute(Qt.WidgetAttribute.WA_NativeWindow))
                self.assertFalse(pages.testAttribute(Qt.WidgetAttribute.WA_NativeWindow))
                self.assertFalse(tab.view._native_visible)
                self.assertFalse(tab.view._filter_installed)
            finally:
                tab.dispose()
                window.close()
                window.deleteLater()
                QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == '__main__':
    unittest.main()
