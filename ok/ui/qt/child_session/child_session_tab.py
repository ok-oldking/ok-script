"""The Child Session page: run the game in a nested Windows session so automation
never moves the user's own mouse or keyboard.

The child session lives and dies with ok-script: Start signs it in (or reuses one),
Stop signs it out, and quitting ok-script signs it out too (``DeviceManager.close``).
Shown only when the app config has a ``child_session`` section.
"""

import threading

import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QRect, QTimer, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ok.child_session import credentials, host, win_api
from ok.core.events import communicate
from ok.ui.qt.child_session.rdp_view import RdpView
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.cards import SettingGroup, SettingRow
from ok.ui.qt.kit.dialogs import Dialog, confirm
from ok.ui.qt.kit.feedback import Pill, show_toast
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.switch import Switch
from ok.ui.qt.kit.theme import theme
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

REFRESH_MS = 2000
AUDIO_CHECK_MS = 700


def _tr(text: str) -> str:
    return QCoreApplication.translate("ChildSessionTab", text)


def _mute_in_background() -> bool:
    """The 'Mute Game while in Background' basic option."""
    try:
        from ok import og
        return bool(og.global_config.get_config('Basic Options').get('Mute Game while in Background'))
    except Exception:
        return False


def _ensure_own_audio_muted(muted: bool) -> None:
    """Make this process's audio sessions match ``muted``.

    The RDP control plays the child session's sound inside ok-script, so muting this
    process mutes it. Windows can recreate the session and restores the mute it last
    saw for this executable, so the actual state is checked each time instead of
    remembering what was set."""
    import os
    try:
        from pycaw.api.audioclient import ISimpleAudioVolume
        from pycaw.utils import AudioUtilities
        pid = os.getpid()
        for session in AudioUtilities.GetAllSessions():
            if session.Process and session.Process.pid == pid:
                volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                if bool(volume.GetMute()) != bool(muted):
                    volume.SetMute(bool(muted), None)
    except Exception as e:
        logger.warning(f'child session audio mute failed: {e}')


class AspectView(QWidget):
    """Keeps the session view at the session's aspect ratio, centred in the space it gets."""

    def __init__(self, view: QWidget, width: int, height: int, parent=None):
        super().__init__(parent)
        self.view = view
        self.ratio = width / height if height else 16 / 9
        view.setParent(self)
        self.setMinimumSize(320, 180)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width, height = self.width(), self.height()
        if width / max(height, 1) > self.ratio:
            fit_width, fit_height = round(height * self.ratio), height
        else:
            fit_width, fit_height = width, round(width / self.ratio)
        self.view.setGeometry(QRect((width - fit_width) // 2, (height - fit_height) // 2, fit_width, fit_height))


class ChildSessionTab(QWidget):
    status_ready = Signal(dict)

    def __init__(self, config, device_manager, parent=None):
        super().__init__(parent)
        self.setObjectName('child_session_page')
        self.setProperty('skip_transition', True)
        self.app_config = config
        self.device_manager = device_manager
        self.child_config = config.get('child_session') or {}
        self.windows_config = config.get('windows') or {}
        self.resolution = self.child_config.get('resolution', host.DEFAULT_RESOLUTION)
        self.project = host.project_dir()
        self.settings = host.settings()
        self._used_saved_password = False
        self._logged_in = False
        self._starting = False
        self._asking_password = False
        self._error_toast = None
        self._refreshing = False
        self._agent_ready = False
        self._auto_start_checked = False
        self._disposed = False
        self._status = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(Label(_tr('Child Session'), 'display', self))
        self.state_pill = Pill(_tr('Not started'), 'neutral', self)
        header.addWidget(self.state_pill)
        header.addStretch(1)
        self.start_button = Button(_tr('Start'), 'play', 'primary', parent=self)
        self.start_button.clicked.connect(self.toggle_session)
        header.addWidget(self.start_button)
        root.addLayout(header)

        root.addWidget(Label(_tr('Runs the game in a separate Windows session, so tasks never use your mouse and '
                                 'keyboard. Select the ChildSession capture to use it. The session stops when '
                                 'ok-script exits.'), 'secondary', self, word_wrap=True))
        self.info_label = Label('', 'body', self, word_wrap=True)
        root.addWidget(self.info_label)

        self.view = RdpView()
        self.view.set_view_only(False)
        self.view.connected.connect(self._on_connected)
        self.view.login_complete.connect(self._on_login_complete)
        self.view.disconnected.connect(self._on_disconnected)
        self.view.logon_error.connect(self._on_logon_error)
        self.aspect_view = AspectView(self.view, *self.resolution, parent=self)
        root.addWidget(self.aspect_view, 1)

        bar = QHBoxLayout()
        self.settings_button = Button(_tr('Settings'), 'gear', 'subtle', size='small', parent=self)
        self.settings_button.clicked.connect(self._toggle_settings)
        bar.addWidget(self.settings_button)
        bar.addStretch(1)
        bar.addWidget(Label(_tr('View only'), 'secondary', self))
        self.view_only_switch = Switch(bool(self.settings.get('view_only', True)), self)
        self.view_only_switch.toggled.connect(self._set_view_only)
        bar.addWidget(self.view_only_switch)
        root.addLayout(bar)

        self.settings_group = SettingGroup()
        self.enable_button = Button(_tr('Enable'), parent=self)
        self.enable_button.clicked.connect(self.enable_child_sessions)
        self.windows_row = self.settings_group.add_row(
            SettingRow(_tr('Child sessions in Windows'), '-', self.enable_button))
        self.forget_button = Button(_tr('Forget'), 'trash', 'subtle', parent=self)
        self.forget_button.clicked.connect(self.forget_password)
        self.password_row = self.settings_group.add_row(SettingRow(_tr('Saved password'), '-', self.forget_button))
        self.auto_start_switch = Switch(bool(self.settings.get('auto_connect', True)), self)
        self.auto_start_switch.toggled.connect(lambda on: self._set_setting('auto_connect', on))
        self.settings_group.add_row(SettingRow(
            _tr('Start with ok-script'),
            _tr('When the ChildSession capture is selected, start the child session with ok-script.'),
            self.auto_start_switch))
        self.elevate_switch = Switch(bool(self.settings.get('elevate', True)), self)
        self.elevate_switch.toggled.connect(lambda on: self._set_setting('elevate', on))
        self.settings_group.add_row(SettingRow(
            _tr('Run the agent as admin'),
            _tr('Needed when the game runs as admin; Windows asks once per session sign-in.'),
            self.elevate_switch))
        self.close_apps_edit = QLineEdit(', '.join(self.settings.get('close_apps') or []), self)
        self.close_apps_edit.editingFinished.connect(self._save_close_apps)
        self.settings_group.add_row(SettingRow(
            _tr('Close in the child session'),
            _tr('Startup apps to close in the child session only, comma separated.'),
            self.close_apps_edit, control_width=280))
        self.settings_group.setVisible(bool(self.settings.get('settings_open', False)))
        root.addWidget(self.settings_group)

        theme.install(self)
        self.status_ready.connect(self._apply_status)
        communicate.child_session_connect.connect(self._on_start_requested)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)
        # Sound from the child session plays only while this page is in front and the
        # window is shown; otherwise ok-script's own audio session is muted.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._release_audio)
        self.audio_timer = QTimer(self)
        self.audio_timer.timeout.connect(self._update_audio)
        self.audio_timer.start(AUDIO_CHECK_MS)
        try:
            host.sync_agent_config(self.windows_config)
        except Exception as e:
            logger.error('could not write the child session agent config', e)
        self.refresh()

    # --- settings -------------------------------------------------------------

    def _set_setting(self, key, value):
        self.settings[key] = value
        host.sync_agent_config(self.windows_config)

    def _save_close_apps(self):
        names = [name.strip() for name in self.close_apps_edit.text().split(',') if name.strip()]
        self._set_setting('close_apps', names)

    def _toggle_settings(self):
        visible = not self.settings_group.isVisible()
        self.settings_group.setVisible(visible)
        self.settings['settings_open'] = visible

    def _set_view_only(self, on):
        self.settings['view_only'] = on
        self._apply_view_only()

    def _apply_view_only(self):
        """View only blocks the host mouse and keyboard, but only once the agent runs:
        until then the user may need to click the agent's UAC prompt in the session."""
        self.view.set_view_only(self.view_only_switch.isChecked() and self._agent_ready)

    # --- audio ----------------------------------------------------------------

    def _audible(self) -> bool:
        """This page is the current page and the window is shown (not minimized or hidden)."""
        window = self.window()
        shown = (self.view.is_connected and self.isVisible() and window is not None
                 and window.isVisible() and not window.isMinimized())
        if shown and _mute_in_background() and not window.isActiveWindow():
            # The game runs in another session, so the window capture's own
            # background mute cannot reach it; apply the setting here.
            return False
        return shown

    def _update_audio(self):
        # Without a connected session nothing of the child session plays: stay unmuted.
        _ensure_own_audio_muted(self.view.is_connected and not self._audible())

    def _release_audio(self):
        """Leave ok-script unmuted; Windows would otherwise remember the mute for this
        executable at its next start, and for other apps run by the same python.exe."""
        _ensure_own_audio_muted(False)

    # --- status ---------------------------------------------------------------

    def _maybe_auto_start(self):
        """Once per run of ok-script: start when the ChildSession capture is selected."""
        if self._disposed or self._auto_start_checked or self.view.is_connected or self._starting:
            return
        window = self.window()
        if window is None or window is self:
            return  # wait until mounted in MainWindow so AtlAxWin parents to the top-level window
        if self.device_manager.get_preferred_device() is None:
            return  # devices not refreshed yet; try on the next tick
        self._auto_start_checked = True
        try:
            selected = self.device_manager.uses_child_session()
        except Exception:
            selected = False
        if selected and self.settings.get('auto_connect', True) and win_api.is_enabled():
            logger.info('child session auto start')
            self.start_session()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ParentChange and not self._auto_start_checked and not self._disposed:
            QTimer.singleShot(0, self, self._maybe_auto_start)

    def refresh(self):
        self._maybe_auto_start()
        if self._refreshing:
            return
        self._refreshing = True
        threading.Thread(target=self._collect_status, daemon=True, name='ChildSessionStatus').start()

    def _collect_status(self):
        status = {}
        try:
            status['enabled'] = win_api.is_enabled()
            session = win_api.child_session_id()
            status['session'] = session
            status['state'] = win_api.session_state(session) if session is not None else None
            saved = credentials.load()
            status['saved_user'] = saved[0] if saved else None
            status['agent'] = self.device_manager.child_session_client().try_call('window_info')
        except Exception as e:
            logger.error('child session status failed', e)
        finally:
            self.status_ready.emit(status)

    def _apply_status(self, status):
        self._refreshing = False
        self._status = status
        info = status.get('agent')
        session = status.get('session')
        self._agent_ready = bool(info) and (info.get('elevated') or not self.settings.get('elevate', True))
        self._apply_view_only()

        running = self.view.is_connected or self._starting
        self.start_button.setText(_tr('Stop') if running else _tr('Start'))
        self.start_button.set_icon('stop' if running else 'play')
        self.start_button.set_variant('danger' if running else 'primary')
        if self._starting and not self.view.is_connected:
            self.state_pill.setText(_tr('Starting'))
            self.state_pill.set_tone('accent')
        elif self.view.is_connected and info:
            self.state_pill.setText(_tr('Running'))
            self.state_pill.set_tone('success')
        elif self.view.is_connected:
            self.state_pill.setText(_tr('Starting'))
            self.state_pill.set_tone('accent')
        else:
            self.state_pill.setText(_tr('Not started'))
            self.state_pill.set_tone('neutral')

        parts = []
        if session is not None:
            parts.append(_tr('Session {id}').format(id=session))
        if info:
            parts.append(_tr('agent: {admin}').format(
                admin=_tr('admin') if info.get('elevated') else _tr('not admin')))
            if info.get('exists'):
                parts.append(_tr('game: {title} {width}x{height}').format(
                    title=(info.get('title') or '').strip(), width=info.get('width'), height=info.get('height')))
            else:
                parts.append(_tr('game: not started'))
        elif session is not None:
            parts.append(_tr('agent: starting, about a minute after sign-in'))
        if not status.get('enabled', True):
            parts.append(_tr('Child sessions are off in Windows. Enable them in Settings.'))
        self.info_label.setText(' · '.join(parts) or _tr('Press Start to sign in the child session.'))

        enabled = status.get('enabled')
        self.windows_row.description_label.setText(_tr('Enabled') if enabled else _tr('Off. Needs admin once.'))
        self.enable_button.setVisible(not enabled)
        saved_user = status.get('saved_user')
        self.password_row.description_label.setText(
            _tr('Saved for {user}').format(user=saved_user) if saved_user else _tr('Not saved'))
        self.forget_button.setEnabled(bool(saved_user))

    # --- actions --------------------------------------------------------------

    def enable_child_sessions(self):
        if not win_api.is_elevated():
            show_toast(self, _tr('Enabling child sessions needs admin. Restart this app as admin and try again.'),
                       tone='warning')
            return
        if win_api.enable(True):
            show_toast(self, _tr('Child sessions enabled.'), tone='success')
        else:
            show_toast(self, _tr('Windows refused to enable child sessions.'), tone='danger')
        self.refresh()

    def _clear_error_toast(self):
        toast = self._error_toast
        self._error_toast = None
        if toast is not None and shiboken6.isValid(toast):
            try:
                toast.close()
            except RuntimeError:
                pass

    def forget_password(self):
        credentials.forget()
        self._clear_error_toast()
        self.refresh()

    def _ask_password(self):
        """Ask for the password once; the user name is detected. Returns (user, password) or None."""
        user_name = win_api.sign_in_name()
        dialog = Dialog(self, _tr('Child session sign-in'),
                        _tr('Enter your Windows account password (not the PIN). For a Microsoft account, '
                            'this is the Microsoft account password. It is saved in Windows Credential Manager.'),
                        ok_text=_tr('Sign in'))
        user = QLineEdit(user_name, dialog.panel)
        user.setReadOnly(True)
        password = QLineEdit(dialog.panel)
        password.setEchoMode(QLineEdit.EchoMode.Password)
        password.setPlaceholderText(_tr('Password'))
        dialog.body.addWidget(user)
        dialog.body.addWidget(password)
        QTimer.singleShot(0, password.setFocus)
        try:
            if not dialog.exec() or not password.text():
                return None
            credentials.save(user_name, password.text())
            return user_name, password.text()
        finally:
            dialog.deleteLater()

    def start_session(self):
        """Sign in the child session (or reuse one), install the agent autostart, show it."""
        if self.view.is_connected or self._starting or self._asking_password:
            return
        window = self.window()
        if window is None or window is self:
            # The RDP control parents to the top-level window; creating it now would
            # make this tab a native top-level window of its own.
            logger.warning('child session start ignored: the page is not in a window yet')
            return
        if not win_api.is_enabled():
            show_toast(self, _tr('Child sessions are off in Windows. Enable them in Settings.'), tone='warning')
            self.settings_group.setVisible(True)
            return
        self._clear_error_toast()
        host.sync_agent_config(self.windows_config)
        host.install_autostart(self.project)
        saved = credentials.load()
        self._used_saved_password = saved is not None
        if saved is None:
            self._asking_password = True
            try:
                saved = self._ask_password()
            finally:
                self._asking_password = False
            if saved is None:
                return
        self._logged_in = False
        self._starting = True
        logger.info('child session start requested')
        try:
            self.view.connect_session(*self.resolution, saved[0], saved[1])
        except Exception as e:
            self._starting = False
            logger.error('child session start failed', e)
            show_toast(self, _tr('Could not start the session view: {error}').format(error=e), tone='danger')
        self.refresh()

    def stop_session(self):
        """Sign out the child session; this closes the game running in it."""
        info = self._status.get('agent') or {}
        if info.get('exists') and not confirm(
                self, _tr('Stop the child session?'),
                _tr('Closes the game in the child session. It also stops when ok-script exits.'),
                ok_text=_tr('Stop'), danger=True):
            return
        self._starting = False
        self.view.disconnect_session()
        session = win_api.child_session_id()
        if session is not None and not win_api.logoff(session, wait=False):
            show_toast(self, _tr('Windows refused to sign out the child session.'), tone='danger')
        logger.info(f'child session {session} stopped')
        self._release_audio()
        self.refresh()

    def toggle_session(self):
        if self.view.is_connected or self._starting:
            self.stop_session()
        else:
            self.start_session()

    def _on_start_requested(self):
        """A task start needs the agent: start the child session if it is not running."""
        if not self.view.is_connected:
            self.start_session()

    # --- viewer events --------------------------------------------------------

    def _on_connected(self):
        self._starting = False
        self.refresh()

    def _on_login_complete(self):
        self._logged_in = True
        self.refresh()

    def _on_logon_error(self, code):
        logger.warning(f'child session logon error {code}')

    def _on_disconnected(self, reason):
        if self._starting and not self._logged_in and self._used_saved_password:
            # Do not retry a saved password that failed: repeated failures can lock the account.
            self._clear_error_toast()
            self._error_toast = show_toast(
                self, _tr('Sign-in failed (code {code}). If your password changed, forget the saved '
                          'password and connect again.').format(code=reason),
                tone='danger', duration=0,
                action=(_tr('Forget password'), self.forget_password))
        self._starting = False
        self._logged_in = False
        self._release_audio()
        self.refresh()

    def dispose(self):
        self._disposed = True
        self.timer.stop()
        self.audio_timer.stop()
        self._clear_error_toast()
        app = QApplication.instance()
        if app is not None:
            try:
                app.aboutToQuit.disconnect(self._release_audio)
            except Exception:
                pass
        self._release_audio()
        try:
            communicate.child_session_connect.disconnect(self._on_start_requested)
        except Exception:
            pass
        self.view.dispose()
