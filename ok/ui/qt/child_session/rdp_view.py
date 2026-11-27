"""The child session's screen, embedded in a Qt widget.

ok-script ships a minimal PySide6 build without QtAxContainer, so the RDP ActiveX
control is hosted in Windows' own ATL container (``AtlAxWin``, atl.dll) through
comtypes and parented directly to the top-level window's native handle so Qt's
alien widget hierarchy (and in-window overlays) stays non-native.
"""

import ctypes
from ctypes import wintypes

import shiboken6
from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QRegion
from PySide6.QtWidgets import QApplication, QWidget

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

RDP_CLSID = '{8B918B82-7985-4C24-89DF-C33AD2BBFBCD}'  # MsRdpClient9NotSafeForScripting
WS_CHILD, WS_CLIPCHILDREN = 0x40000000, 0x02000000
SW_HIDE, SW_SHOWNA = 0, 8
RGN_ERROR, RGN_OR = 0, 2
# OnLogonError codes that are informational, not failures.
LOGON_INFO_CODES = (-2,)
# Never include ChildAdded: it fires mid-C++-ctor and touching event.child() corrupts Shiboken6 subclasses.
_SYNC_EVENTS = frozenset({
    QEvent.Type.Show,
    QEvent.Type.Hide,
    QEvent.Type.Move,
    QEvent.Type.Resize,
    QEvent.Type.ZOrderChange,
    QEvent.Type.Close,
    QEvent.Type.ChildRemoved,
    QEvent.Type.DevicePixelRatioChange,
})

_USER32 = None
_GDI32 = None


def _user32():
    global _USER32
    if _USER32 is None:
        lib = ctypes.WinDLL('user32', use_last_error=True)
        lib.CreateWindowExW.restype = wintypes.HWND
        lib.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
        ]
        lib.MoveWindow.restype = wintypes.BOOL
        lib.MoveWindow.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.BOOL]
        lib.ShowWindow.restype = wintypes.BOOL
        lib.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        lib.SetWindowRgn.restype = ctypes.c_int
        lib.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
        lib.SetParent.restype = wintypes.HWND
        lib.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
        lib.EnableWindow.restype = wintypes.BOOL
        lib.EnableWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
        lib.DestroyWindow.restype = wintypes.BOOL
        lib.DestroyWindow.argtypes = [wintypes.HWND]
        _USER32 = lib
    return _USER32


def _gdi32():
    global _GDI32
    if _GDI32 is None:
        lib = ctypes.WinDLL('gdi32', use_last_error=True)
        lib.CreateRectRgn.restype = wintypes.HRGN
        lib.CreateRectRgn.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        lib.CombineRgn.restype = ctypes.c_int
        lib.CombineRgn.argtypes = [wintypes.HRGN, wintypes.HRGN, wintypes.HRGN, ctypes.c_int]
        lib.DeleteObject.restype = wintypes.BOOL
        lib.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        _GDI32 = lib
    return _GDI32


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
        self._parent_hwnd = None
        self._rdp = None
        self._events = None
        self._event_connection = None
        self._view_only = False
        self._session_active = False
        self._native_visible = False
        self._last_native_rect = None
        self._applied_region = None
        self._applied_ratio = None
        self._filter_installed = False
        self._sync_pending = False
        self.is_connected = False
        self.connected.connect(self._on_connected)
        self.disconnected.connect(self._on_disconnected)

    def _on_connected(self):
        # Also covers the control reconnecting on its own after a reported disconnect.
        self.is_connected = True
        self._session_active = True
        self._sync_native_window()

    def _on_disconnected(self, reason):
        self.is_connected = False
        self._session_active = False
        self._sync_native_window()
        logger.info(f'child session viewer disconnected, reason {reason}')

    def _create_control(self):
        if self._rdp is not None:
            return
        import comtypes
        mstsc = _mstsc()
        user32 = _user32()
        atl = ctypes.WinDLL('atl')
        atl.AtlAxWinInit()
        window = self.window()
        parent_hwnd = int(window.winId())
        x, y, width, height = self._native_rect()
        hwnd = user32.CreateWindowExW(0, 'AtlAxWin', RDP_CLSID, WS_CHILD | WS_CLIPCHILDREN,
                                      x, y, width, height, parent_hwnd, None, None, None)
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        unknown = ctypes.POINTER(comtypes.IUnknown)()
        result = atl.AtlAxGetControl(wintypes.HWND(hwnd), ctypes.byref(unknown))
        if result != 0:
            user32.DestroyWindow(wintypes.HWND(hwnd))
            raise OSError(f'AtlAxGetControl failed: {result:#x}')
        self._hwnd = hwnd
        self._parent_hwnd = parent_hwnd
        self._last_native_rect = (x, y, width, height)
        self._native_visible = False
        self._applied_region = None
        self._applied_ratio = None
        try:
            self._rdp = unknown.QueryInterface(mstsc.IMsRdpClient9)
            import comtypes.client
            self._events = _Events(self)
            self._event_connection = comtypes.client.GetEvents(self._rdp, self._events,
                                                               interface=mstsc.IMsTscAxEvents)
        except Exception:
            # Leave no half-built control behind: the next connect creates a fresh one.
            self._event_connection = None
            self._events = None
            self._rdp = None
            self._hwnd = None
            self._parent_hwnd = None
            self._last_native_rect = None
            user32.DestroyWindow(wintypes.HWND(hwnd))
            raise
        self.set_view_only(self._view_only)
        logger.info(f'RDP control created, version {self._rdp.Version}')

    def connect_session(self, width: int, height: int, user_name: str, password: str):
        """Connect to this user's child session at ``width`` x ``height``."""
        self._create_control()
        rdp = self._rdp
        if self.is_connected:
            self._session_active = True
            self._sync_native_window()
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
        self._session_active = True
        self._sync_native_window()
        try:
            rdp.Connect()
        except Exception:
            self._session_active = False
            self._sync_native_window()
            raise

    def disconnect_session(self):
        self._session_active = False
        self._sync_native_window()
        if self._rdp is not None and self.is_connected:
            try:
                self._rdp.Disconnect()
            except Exception as e:
                logger.error('RDP disconnect failed', e)

    def set_view_only(self, view_only: bool):
        """Block the host mouse and keyboard from reaching the session; it keeps drawing."""
        self._view_only = bool(view_only)
        if self._hwnd:
            _user32().EnableWindow(wintypes.HWND(self._hwnd), not self._view_only)

    def _window_offset(self) -> QPoint:
        """This widget's top-left in logical pixels relative to its top-level window."""
        window = self.window()
        return self.mapTo(window, QPoint(0, 0)) if window is not None and window is not self else QPoint(0, 0)

    def _ancestor_clip(self) -> QRect:
        """The part of this widget its ancestors leave visible, in view coordinates.

        The native window is a child of the top-level window, so unlike an alien
        widget it is not clipped by its Qt ancestors; clip it here instead.
        """
        clip = self.rect()
        parent = self.parentWidget()
        while parent is not None:
            clip = clip.intersected(QRect(self.mapFrom(parent, QPoint(0, 0)), parent.size()))
            if parent.isWindow():
                break
            parent = parent.parentWidget()
        return clip

    def _native_rect(self) -> tuple[int, int, int, int]:
        """This widget's rectangle in physical pixels relative to its top-level window."""
        window = self.window()
        ratio = window.devicePixelRatioF() if window is not None else self.devicePixelRatioF()
        top_left = self._window_offset()
        return (
            round(top_left.x() * ratio),
            round(top_left.y() * ratio),
            max(round(self.width() * ratio), 1),
            max(round(self.height() * ratio), 1),
        )

    def _win32_move(self, x: int, y: int, width: int, height: int) -> None:
        _user32().MoveWindow(wintypes.HWND(self._hwnd), x, y, width, height, True)

    def _win32_show(self, visible: bool) -> None:
        _user32().ShowWindow(wintypes.HWND(self._hwnd), SW_SHOWNA if visible else SW_HIDE)

    def _win32_set_parent(self, parent_hwnd: int) -> None:
        _user32().SetParent(wintypes.HWND(self._hwnd), wintypes.HWND(parent_hwnd))

    def _win32_clear_region(self) -> bool:
        return bool(_user32().SetWindowRgn(wintypes.HWND(self._hwnd), None, True))

    def _win32_set_region(self, visible: QRegion, ratio: float) -> bool:
        gdi32 = _gdi32()
        hrgn = gdi32.CreateRectRgn(0, 0, 0, 0)
        if not hrgn:
            return False
        # Round in window coordinates, as _native_rect does for the window position,
        # so region edges land on the same physical pixels as overlay edges.
        offset = self._window_offset()
        ox, oy = offset.x(), offset.y()
        x0, y0 = round(ox * ratio), round(oy * ratio)
        for rect in visible:
            sub = gdi32.CreateRectRgn(
                round((rect.left() + ox) * ratio) - x0,
                round((rect.top() + oy) * ratio) - y0,
                round((rect.right() + 1 + ox) * ratio) - x0,
                round((rect.bottom() + 1 + oy) * ratio) - y0,
            )
            if not sub:
                gdi32.DeleteObject(hrgn)
                return False
            combined = gdi32.CombineRgn(hrgn, hrgn, sub, RGN_OR)
            gdi32.DeleteObject(sub)
            if combined == RGN_ERROR:
                gdi32.DeleteObject(hrgn)
                return False
        if _user32().SetWindowRgn(wintypes.HWND(self._hwnd), hrgn, True):
            return True
        gdi32.DeleteObject(hrgn)
        return False

    def _move_native(self, x: int, y: int, width: int, height: int) -> None:
        rect = (x, y, width, height)
        if self._hwnd and rect != self._last_native_rect:
            self._win32_move(x, y, width, height)
            self._last_native_rect = rect

    def _show_native(self, visible: bool) -> None:
        if self._hwnd and visible != self._native_visible:
            self._win32_show(visible)
            self._native_visible = visible

    def _clear_native_region(self) -> bool:
        if self._applied_region is None:
            return True
        if not self._hwnd:
            self._applied_region = None
            self._applied_ratio = None
            return True
        if self._win32_clear_region():
            self._applied_region = None
            self._applied_ratio = None
            return True
        return False

    def _apply_native_region(self, visible: QRegion) -> bool:
        window = self.window()
        ratio = window.devicePixelRatioF() if window is not None else self.devicePixelRatioF()
        if self._applied_region == visible and self._applied_ratio == ratio:
            return True
        if not self._hwnd:
            return False
        if self._win32_set_region(visible, ratio):
            self._applied_region = QRegion(visible)
            self._applied_ratio = ratio
            return True
        return False

    def _set_app_filter(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._filter_installed:
            return
        app = QApplication.instance()
        if app is None:
            self._filter_installed = False
            return
        if enabled:
            app.installEventFilter(self)
        else:
            app.removeEventFilter(self)
        self._filter_installed = enabled

    def _schedule_sync(self) -> None:
        if self._sync_pending:
            return
        self._sync_pending = True
        QTimer.singleShot(0, self._run_scheduled_sync)

    def _run_scheduled_sync(self) -> None:
        if not shiboken6.isValid(self):
            return
        self._sync_pending = False
        self._sync_native_window()

    def _overlay_rects(self) -> list[QRect]:
        """Rectangles of visible top-level overlays stacked above this view, in view coordinates."""
        window = self.window()
        if window is None or window is self:
            return []
        branch = self
        while branch.parentWidget() is not None and branch.parentWidget() is not window:
            branch = branch.parentWidget()
        if branch.parentWidget() is not window:
            return []
        siblings = window.children()
        for index, item in enumerate(siblings):
            if item is branch:
                bounds = self.rect()
                rects = []
                for sibling in siblings[index + 1:]:
                    if (isinstance(sibling, QWidget) and not sibling.isWindow()
                            and sibling.isVisibleTo(window) and not sibling.geometry().isEmpty()):
                        top_left = self.mapFrom(window, sibling.geometry().topLeft())
                        rect = QRect(top_left, sibling.size())
                        if rect.intersects(bounds):
                            rects.append(rect.intersected(bounds))
                return rects
        return []

    def _sync_native_window(self):
        """Position, clip, and show or hide the native RDP window around overlays."""
        active_visible = bool(self._hwnd and self._session_active and self.isVisible())
        self._set_app_filter(active_visible)
        if not self._hwnd:
            return
        if not active_visible or self.rect().isEmpty():
            self._clear_native_region()
            self._show_native(False)
            return
        window = self.window()
        if window is not None and window is not self:
            parent_hwnd = int(window.winId())
            if self._parent_hwnd != parent_hwnd:
                self._win32_set_parent(parent_hwnd)
                self._parent_hwnd = parent_hwnd
                self._last_native_rect = None
        bounds = self.rect()
        visible = QRegion(self._ancestor_clip())
        for rect in self._overlay_rects():
            visible -= QRegion(rect)
        if visible.isEmpty():
            self._clear_native_region()
            self._show_native(False)
        elif visible == QRegion(bounds):
            self._move_native(*self._native_rect())
            self._clear_native_region()
            self._show_native(True)
        else:
            self._move_native(*self._native_rect())
            if self._apply_native_region(visible):
                self._show_native(True)
            else:
                self._show_native(False)

    def eventFilter(self, watched, event):
        etype = event.type()
        if etype not in _SYNC_EVENTS:
            return False
        if (not shiboken6.isValid(self) or not self._session_active or not self._hwnd
                or not self.isVisible() or not shiboken6.isValid(watched) or not watched.isWidgetType()):
            return False
        window = self.window()
        if window is None or window is self:
            return False
        if watched is not window:
            if watched.isWindow() or watched.window() is not window:
                return False
            if watched.parentWidget() is not window and not watched.isAncestorOf(self):
                return False
        if etype == QEvent.Type.DevicePixelRatioChange:
            self._last_native_rect = None
        self._schedule_sync()
        return False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_native_window()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._sync_native_window()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_native_window()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._sync_native_window()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.ParentChange, QEvent.Type.DevicePixelRatioChange):
            self._last_native_rect = None
            self._sync_native_window()

    def dispose(self):
        self._set_app_filter(False)
        self.disconnect_session()
        self._event_connection = None
        self._rdp = None
        if self._hwnd:
            _user32().DestroyWindow(wintypes.HWND(self._hwnd))
            self._hwnd = None
        self._parent_hwnd = None
        self._native_visible = False
        self._last_native_rect = None
        self._applied_region = None
        self._applied_ratio = None
