"""A frameless top-level window with a kit title bar.

On Windows the native frame styles are kept (so snapping, Aero shake,
minimize/maximize animations and the drop shadow still work) while
``WM_NCCALCSIZE`` hands the whole window to the client area and
``WM_NCHITTEST`` reports resize borders, the caption and the maximize button
(for Windows 11 snap layouts). Other platforms use the native frame and hide
the kit window buttons.
"""

import ctypes
import sys

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPen, QRegion
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.mica import paint_mica
from ok.ui.qt.kit.theme import SYSTEMBACKDROP_MIN_BUILD, Backdrop, theme

IS_WINDOWS = sys.platform == "win32"

WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCACTIVATE = 0x0086
WM_NCMOUSEMOVE = 0x00A0
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP = 0x00A2
WM_NCMOUSELEAVE = 0x02A2
WM_DWMCOMPOSITIONCHANGED = 0x031E

HTCLIENT, HTCAPTION, HTMAXBUTTON = 1, 2, 9
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 10, 11, 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17

GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2
DWMWA_SYSTEMBACKDROP_TYPE = 38  # Windows 11 22H2 (build 22621) and later
DWMSBT_NONE, DWMSBT_MAINWINDOW, DWMSBT_TRANSIENTWINDOW = 1, 2, 3  # none, Mica, Acrylic
DWMWA_MICA_EFFECT = 1029  # undocumented, Windows 11 21H2
SYSTEMBACKDROP_TYPES = {Backdrop.NONE: DWMSBT_NONE, Backdrop.MICA: DWMSBT_MAINWINDOW,
                        Backdrop.ACRYLIC: DWMSBT_TRANSIENTWINDOW}

RESIZE_BORDER = 6
TITLE_BAR_HEIGHT = 44


class _Rect(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _NcCalcSizeParams(ctypes.Structure):
    _fields_ = [("rgrc", _Rect * 3), ("lppos", ctypes.c_void_p)]


class _Margins(ctypes.Structure):
    _fields_ = [("left", ctypes.c_int), ("right", ctypes.c_int), ("top", ctypes.c_int), ("bottom", ctypes.c_int)]


class _Msg(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint), ("wParam", ctypes.c_size_t),
                ("lParam", ctypes.c_ssize_t), ("time", ctypes.c_ulong), ("pt_x", ctypes.c_long),
                ("pt_y", ctypes.c_long)]


def _def_window_proc(hwnd, message, wparam, lparam) -> int:
    proc = ctypes.windll.user32.DefWindowProcW
    proc.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    proc.restype = ctypes.c_ssize_t
    return proc(hwnd, message, wparam, lparam)


def _signed_word(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


class WindowButton(QAbstractButton):
    """A caption button (minimize, maximize/restore, close)."""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(46, TITLE_BAR_HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._native_hover = False
        self._icon_name = f"window-{kind}"
        theme.changed.connect(self.update)

    def set_icon_name(self, name: str) -> None:
        self._icon_name = name
        self.update()

    def set_native_hover(self, hover: bool) -> None:
        if hover != self._native_hover:
            self._native_hover = hover
            self.update()

    def paintEvent(self, _event) -> None:
        from ok.ui.qt.kit.icons import icon
        painter = QPainter(self)
        hovered = self.underMouse() or self._native_hover
        if self.kind == "close" and hovered:
            painter.fillRect(self.rect(), Qt.GlobalColor.red if self.isDown() else theme.color("danger"))
            color = "#FFFFFF"
        else:
            if hovered:
                painter.fillRect(self.rect(), theme.color("control_pressed" if self.isDown() else "control_hover"))
            color = "text_secondary"
        side = 14
        pixmap = icon(self._icon_name, color, 1.4).pixmap(QSize(side, side), self.devicePixelRatioF())
        painter.drawPixmap(QPoint((self.width() - side) // 2, (self.height() - side) // 2), pixmap)


class TitleBar(QWidget):
    """Window icon, title, an optional badge and the caption buttons.

    Widgets put in :attr:`content` (e.g. a search field) stay clickable; the
    rest of the bar drags the window.
    """

    def __init__(self, window: QWidget):
        super().__init__(window)
        self.setObjectName("kitTitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(TITLE_BAR_HEIGHT)
        self._window = window

        self.icon_label = QLabel(self)
        self.icon_label.setFixedSize(22, 22)
        self.icon_label.setScaledContents(True)
        self.title_label = Label("", "strong")
        self.badge_label = Label("", "caption")
        self.badge_label.setObjectName("titleBadge")
        self.badge_label.hide()
        self.content = QHBoxLayout()
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(8)

        self.minimize_button = WindowButton("minimize", self)
        self.maximize_button = WindowButton("maximize", self)
        self.close_button = WindowButton("close", self)
        self.minimize_button.clicked.connect(window.showMinimized)
        self.maximize_button.clicked.connect(self.toggle_maximized)
        self.close_button.clicked.connect(window.close)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.badge_label, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)
        layout.addLayout(self.content)
        layout.addStretch(1)
        for button in (self.minimize_button, self.maximize_button, self.close_button):
            layout.addWidget(button)
            button.setVisible(IS_WINDOWS)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_badge(self, text: str) -> None:
        self.badge_label.setText(text or "")
        self.badge_label.setVisible(bool(text))

    def set_icon(self, icon) -> None:
        self.icon_label.setPixmap(icon.pixmap(QSize(22, 22), self.devicePixelRatioF()))

    def toggle_maximized(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def sync_state(self) -> None:
        self.maximize_button.set_icon_name("window-restore" if self._window.isMaximized() else "window-maximize")

    def is_drag_area(self, pos: QPoint) -> bool:
        """Whether ``pos`` (title bar coordinates) should move the window."""

        if not self.rect().contains(pos):
            return False
        child = self.childAt(pos)
        while child is not None and child is not self:
            if isinstance(child, QAbstractButton) or child.focusPolicy() != Qt.FocusPolicy.NoFocus:
                return False
            child = child.parentWidget()
        return True

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.is_drag_area(event.position().toPoint()):
            self.toggle_maximized()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        # Native hit-testing drags the window on Windows; elsewhere ask Qt.
        if not IS_WINDOWS and event.button() == Qt.MouseButton.LeftButton \
                and self.is_drag_area(event.position().toPoint()) and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()
        super().mousePressEvent(event)


class ContentLayer(QWidget):
    """The panel page content sits on, inside a window's frame.

    With a backdrop (Mica, Acrylic) it is an opaque sheet with a rounded
    top-left corner and a hairline edge, so the material shows only around
    it. Without one it paints nothing and the window color shows through.
    """

    RADIUS = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("kitContentLayer")
        theme.changed.connect(self.update)

    def paintEvent(self, _event) -> None:
        fill = theme.background("layer")
        if fill.alpha() == 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        edge = theme.color("border")
        # Extend past the right and bottom edges so only the top-left corner is rounded.
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, self.RADIUS * 2, self.RADIUS * 2)
        painter.setPen(QPen(edge, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)


class KitWindow(QWidget):
    """A top-level window: kit title bar on top, :attr:`body` below."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        if IS_WINDOWS:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.title_bar = TitleBar(self)
        self.body = QWidget(self)
        self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.title_bar)
        layout.addWidget(self.body, 1)
        self._native_ready = False
        self._backdrop = None  # unknown until the native frame is set up
        self._backdrop_on = False
        theme.install(self.title_bar)
        theme.changed.connect(self._on_kit_theme_changed)
        # Create the native window now; callers read windowHandle() before the first show.
        self.winId()

    def setWindowTitle(self, title: str) -> None:
        super().setWindowTitle(title)
        self.title_bar.set_title(title)

    def setWindowIcon(self, icon) -> None:
        super().setWindowIcon(icon)
        self.title_bar.set_icon(icon)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        # Replace rather than blend, so a translucent fill lets the backdrop through.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), theme.background("window"))
        if self._draws_mica():
            # DWM gives a window one backdrop: with Acrylic only the title bar keeps
            # it, and everything below (run bar, sidebar, the content layer's corner)
            # shows Mica drawn from the wallpaper, under the Mica frame tint.
            body = self.body.geometry()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            paint_mica(painter, self, body, theme.is_dark())
            painter.fillRect(body, theme.frame_tint(Backdrop.MICA))

    def showEvent(self, event) -> None:
        if IS_WINDOWS and not self._native_ready:
            self._native_ready = True
            self._init_native_frame()
        super().showEvent(event)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            self.title_bar.sync_state()
        elif event.type() == event.Type.ActivationChange and self._draws_mica():
            self.update(self._mica_region())  # Mica turns flat while the window is inactive

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self._draws_mica():
            self.update(self._mica_region())  # the wallpaper under the window changed

    # --- Mica drawn by the app (Acrylic mode) ---------------------------------

    def _draws_mica(self) -> bool:
        return theme.backdrop() == Backdrop.ACRYLIC

    def _mica_region(self) -> QRegion:
        """Where the drawn Mica shows: the body, minus content layers except their rounded corner band."""

        region = QRegion(self.body.geometry())
        for layer in self.findChildren(ContentLayer):
            if layer.isVisible():
                inner = QRect(layer.mapTo(self, QPoint(0, 0)), layer.size())
                region -= QRegion(inner.adjusted(ContentLayer.RADIUS, ContentLayer.RADIUS, 0, 0))
        return region

    def _on_kit_theme_changed(self) -> None:
        self.update()
        if IS_WINDOWS and self._native_ready:
            self._apply_dark_frame()
            self._apply_backdrop()

    # --- Windows native frame -------------------------------------------------

    def _hwnd(self) -> int:
        return int(self.winId())

    def _is_zoomed(self) -> bool:
        # Native messages arrive before Qt syncs its window state, so isMaximized()
        # is stale mid-transition (e.g. restoring by double-clicking the title bar).
        return bool(ctypes.windll.user32.IsZoomed(self._hwnd()))

    def _init_native_frame(self) -> None:
        user32 = ctypes.windll.user32
        hwnd = self._hwnd()
        user32.GetWindowLongW.restype = ctypes.c_long
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        user32.SetWindowLongW(hwnd, GWL_STYLE,
                              style | WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)
        self._apply_dark_frame()
        self._apply_backdrop()
        preference = ctypes.c_int(DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(preference),
                                                   ctypes.sizeof(preference))
        # SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0004 | 0x0020)

    def _extend_frame(self) -> None:
        # With a backdrop the frame covers the whole client area so it shows
        # behind it. Extending from the bottom edge (not with -1 margins) keeps DWM
        # from drawing its own caption buttons behind the translucent title bar.
        margins = _Margins(0, 0, 0, 32767) if self._backdrop_on else _Margins(0, 0, 1, 0)
        ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(self._hwnd(), ctypes.byref(margins))

    def _apply_backdrop(self) -> None:
        backdrop = theme.backdrop()
        if backdrop == self._backdrop:
            return
        self._backdrop = backdrop
        enabled = self._backdrop_on = backdrop != Backdrop.NONE
        hwnd = self._hwnd()
        if sys.getwindowsversion().build >= SYSTEMBACKDROP_MIN_BUILD:
            attribute, value = DWMWA_SYSTEMBACKDROP_TYPE, ctypes.c_int(SYSTEMBACKDROP_TYPES[backdrop])
        else:  # only Mica is supported here
            attribute, value = DWMWA_MICA_EFFECT, ctypes.c_int(1 if enabled else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
        self._extend_frame()
        if enabled:
            # Tell DWM the current activation state; until the next WM_NCACTIVATE it
            # would otherwise draw the inactive fill.
            active = ctypes.windll.user32.GetForegroundWindow() == hwnd
            _def_window_proc(hwnd, WM_NCACTIVATE, int(active), 0)
        self.update()

    def _apply_dark_frame(self) -> None:
        value = ctypes.c_int(1 if theme.is_dark() else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(self._hwnd(), DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value),
                                                   ctypes.sizeof(value))

    def _frame_thickness(self) -> tuple:
        user32 = ctypes.windll.user32
        try:
            dpi = user32.GetDpiForWindow(self._hwnd())
            frame_x = user32.GetSystemMetricsForDpi(32, dpi) + user32.GetSystemMetricsForDpi(92, dpi)
            frame_y = user32.GetSystemMetricsForDpi(33, dpi) + user32.GetSystemMetricsForDpi(92, dpi)
        except AttributeError:
            frame_x = user32.GetSystemMetrics(32) + user32.GetSystemMetrics(92)
            frame_y = user32.GetSystemMetrics(33) + user32.GetSystemMetrics(92)
        return frame_x, frame_y

    def _hit_test(self, screen_x: int, screen_y: int) -> int:
        hwnd = self._hwnd()
        point = _Point(screen_x, screen_y)
        ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(point))
        client = _Rect()
        ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(client))
        ratio = self.devicePixelRatioF()
        x, y = point.x / ratio, point.y / ratio
        w, h = client.right / ratio, client.bottom / ratio
        if not self._is_zoomed() and not self.isFullScreen():
            border = RESIZE_BORDER
            left, right, top, bottom = x < border, x >= w - border, y < border, y >= h - border
            if top and left:
                return HTTOPLEFT
            if top and right:
                return HTTOPRIGHT
            if bottom and left:
                return HTBOTTOMLEFT
            if bottom and right:
                return HTBOTTOMRIGHT
            if left:
                return HTLEFT
            if right:
                return HTRIGHT
            if top:
                return HTTOP
            if bottom:
                return HTBOTTOM
        local = QPoint(int(x), int(y))
        bar = self.title_bar
        if bar.maximize_button.isVisible() and bar.maximize_button.geometry().translated(bar.pos()).contains(local):
            return HTMAXBUTTON
        if bar.is_drag_area(bar.mapFrom(self, local)):
            return HTCAPTION
        return HTCLIENT

    def nativeEvent(self, event_type, message):
        if not IS_WINDOWS or event_type != b"windows_generic_MSG":
            return super().nativeEvent(event_type, message)
        msg = _Msg.from_address(int(message))
        if msg.message == WM_NCCALCSIZE and msg.wParam:
            if ctypes.windll.user32.IsZoomed(msg.hwnd):
                params = _NcCalcSizeParams.from_address(msg.lParam)
                frame_x, frame_y = self._frame_thickness()
                rect = params.rgrc[0]
                rect.left += frame_x
                rect.top += frame_y
                rect.right -= frame_x
                rect.bottom -= frame_y
            return True, 0
        if msg.message == WM_NCACTIVATE and self._backdrop_on:
            # Qt passes lParam=-1 to DefWindowProc for frameless windows, which keeps
            # DWM from tracking activation, so the backdrop stays on its flat inactive fill.
            return True, _def_window_proc(msg.hwnd, msg.message, msg.wParam, msg.lParam)
        if msg.message == WM_NCHITTEST:
            result = self._hit_test(_signed_word(msg.lParam), _signed_word(msg.lParam >> 16))
            self.title_bar.maximize_button.set_native_hover(result == HTMAXBUTTON)
            return True, result
        if msg.message == WM_NCLBUTTONDOWN and msg.wParam == HTMAXBUTTON:
            self.title_bar.maximize_button.setDown(True)
            return True, 0
        if msg.message == WM_NCLBUTTONUP and msg.wParam == HTMAXBUTTON:
            self.title_bar.maximize_button.setDown(False)
            self.title_bar.toggle_maximized()
            return True, 0
        if msg.message in (WM_NCMOUSELEAVE, WM_NCMOUSEMOVE) and msg.wParam != HTMAXBUTTON:
            self.title_bar.maximize_button.set_native_hover(False)
            self.title_bar.maximize_button.setDown(False)
        if msg.message == WM_DWMCOMPOSITIONCHANGED:
            self._extend_frame()
        return super().nativeEvent(event_type, message)
