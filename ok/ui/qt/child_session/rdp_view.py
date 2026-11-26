"""The child session's screen, embedded in a Qt widget.

ok-script ships a minimal PySide6 build without QtAxContainer, so the RDP ActiveX
control is hosted in Windows' own ATL container (``AtlAxWin``, atl.dll) through
comtypes and parented to this widget's native window.
"""

import ctypes
from ctypes import wintypes

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

RDP_CLSID = '{8B918B82-7985-4C24-89DF-C33AD2BBFBCD}'  # MsRdpClient9NotSafeForScripting
WS_CHILD, WS_VISIBLE, WS_CLIPCHILDREN = 0x40000000, 0x10000000, 0x02000000
# OnLogonError codes that are informational, not failures.
LOGON_INFO_CODES = (-2,)


def _mstsc():
    import comtypes.client
    return comtypes.client.GetModule(r'C:\Windows\System32\mstscax.dll')


class _Events:
    """Receives the control's COM events on the GUI thread and re-emits them."""

    def __init__(self, view):
        self.view = view

    def OnConnected(self, *args):
        self.view.connected.emit()

    def OnLoginComplete(self, *args):
        self.view.login_complete.emit()

    def OnDisconnected(self, this, reason):
        self.view.disconnected.emit(int(reason))

    def OnLogonError(self, this, code):
        if int(code) not in LOGON_INFO_CODES:
            self.view.logon_error.emit(int(code))

    def OnFatalError(self, this, code):
        self.view.disconnected.emit(-1000 - int(code))


class RdpView(QWidget):
    connected = Signal()
    login_complete = Signal()
    disconnected = Signal(int)
    logon_error = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 180)
        self._hwnd = None
        self._rdp = None
        self._events = None
        self._event_connection = None
        self._view_only = False
        self.is_connected = False
        self.connected.connect(lambda: setattr(self, 'is_connected', True))
        self.disconnected.connect(self._on_disconnected)

    def _on_disconnected(self, reason):
        self.is_connected = False
        logger.info(f'child session viewer disconnected, reason {reason}')

    def _create_control(self):
        if self._rdp is not None:
            return
        import comtypes
        mstsc = _mstsc()
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        atl = ctypes.WinDLL('atl')
        atl.AtlAxWinInit()
        width, height = self._native_size()
        hwnd = user32.CreateWindowExW(0, 'AtlAxWin', RDP_CLSID, WS_CHILD | WS_VISIBLE | WS_CLIPCHILDREN,
                                      0, 0, width, height, int(self.winId()), None, None, None)
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        unknown = ctypes.POINTER(comtypes.IUnknown)()
        result = atl.AtlAxGetControl(wintypes.HWND(hwnd), ctypes.byref(unknown))
        if result != 0:
            raise OSError(f'AtlAxGetControl failed: {result:#x}')
        self._hwnd = hwnd
        self._rdp = unknown.QueryInterface(mstsc.IMsRdpClient9)
        import comtypes.client
        self._events = _Events(self)
        self._event_connection = comtypes.client.GetEvents(self._rdp, self._events, interface=mstsc.IMsTscAxEvents)
        self.set_view_only(self._view_only)
        logger.info(f'RDP control created, version {self._rdp.Version}')

    def connect_session(self, width: int, height: int, user_name: str, password: str):
        """Connect to this user's child session at ``width`` x ``height``."""
        self._create_control()
        rdp = self._rdp
        if self.is_connected:
            return
        mstsc = _mstsc()
        rdp.Server = 'localhost'
        rdp.UserName = user_name
        rdp.DesktopWidth = int(width)
        rdp.DesktopHeight = int(height)
        advanced = rdp.AdvancedSettings9
        advanced.SmartSizing = True
        advanced.EnableCredSspSupport = True
        advanced.ClearTextPassword = password
        rdp.SecuredSettings3.KeyboardHookMode = 1
        rdp.QueryInterface(mstsc.IMsRdpExtendedSettings).Property['ConnectToChildSession'] = True
        rdp.Connect()

    def disconnect_session(self):
        if self._rdp is not None and self.is_connected:
            try:
                self._rdp.Disconnect()
            except Exception as e:
                logger.error('RDP disconnect failed', e)

    def set_view_only(self, view_only: bool):
        """Block the host mouse and keyboard from reaching the session; it keeps drawing."""
        self._view_only = bool(view_only)
        if self._hwnd:
            ctypes.windll.user32.EnableWindow(wintypes.HWND(self._hwnd), not self._view_only)

    def _native_size(self):
        """The widget size in physical pixels; the native control is not DPI-scaled by Qt."""
        ratio = self.devicePixelRatioF()
        return max(round(self.width() * ratio), 1), max(round(self.height() * ratio), 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._hwnd:
            width, height = self._native_size()
            ctypes.windll.user32.MoveWindow(wintypes.HWND(self._hwnd), 0, 0, width, height, True)

    def dispose(self):
        self.disconnect_session()
        self._event_connection = None
        self._rdp = None
        if self._hwnd:
            ctypes.windll.user32.DestroyWindow(wintypes.HWND(self._hwnd))
            self._hwnd = None
