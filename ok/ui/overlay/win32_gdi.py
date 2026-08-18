"""A click-through Windows overlay rendered with ctypes and Win32 GDI.

Unlike the legacy QWidget overlay, this window owns a small Win32 message loop
and has no Qt dependency.  It can therefore be created by both the Qt app and
the headless/web runtime.
"""

from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes

from ok import Logger, og
from ok.core.events import communicate
from ok.util.handler import ExitEvent, Handler

logger = Logger.get_logger(__name__)

if os.name == "nt":
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    kernel32 = ctypes.windll.kernel32

    WS_POPUP = 0x80000000
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_NOACTIVATE = 0x08000000
    SW_HIDE = 0
    SW_SHOWNOACTIVATE = 4
    HWND_TOPMOST = -1
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    WM_DESTROY = 0x0002
    WM_CLOSE = 0x0010
    WM_QUIT = 0x0012
    WM_NCCREATE = 0x0081
    WM_APP = 0x8000
    WM_RENDER = WM_APP + 17
    INPUT_POLL_INTERVAL = 0.02
    AC_SRC_OVER = 0
    AC_SRC_ALPHA = 1
    BI_RGB = 0
    DIB_RGB_COLORS = 0
    TRANSPARENT = 1
    PS_SOLID = 0
    PS_DASH = 1
    VK_RBUTTON = 0x02
    VK_MENU = 0x12


    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


    class SIZE(ctypes.Structure):
        _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG),
                    ("bottom", wintypes.LONG)]


    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [
            ("BlendOp", ctypes.c_byte),
            ("BlendFlags", ctypes.c_byte),
            ("SourceConstantAlpha", ctypes.c_byte),
            ("AlphaFormat", ctypes.c_byte),
        ]


    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
        ]


    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


    class CREATESTRUCTW(ctypes.Structure):
        _fields_ = [
            ("lpCreateParams", ctypes.c_void_p), ("hInstance", ctypes.c_void_p), ("hMenu", ctypes.c_void_p),
            ("hwndParent", ctypes.c_void_p), ("cy", ctypes.c_int), ("cx", ctypes.c_int), ("y", ctypes.c_int),
            ("x", ctypes.c_int), ("style", ctypes.c_long), ("lpszName", wintypes.LPCWSTR),
            ("lpszClass", wintypes.LPCWSTR), ("dwExStyle", wintypes.DWORD),
        ]


    # ``ctypes.wintypes`` does not expose LRESULT on every Python build.
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int), ("hInstance", ctypes.c_void_p), ("hIcon", ctypes.c_void_p),
            ("hCursor", ctypes.c_void_p), ("hbrBackground", ctypes.c_void_p),
            ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
        ]


    # Explicit signatures are essential on 64-bit Python: ctypes otherwise
    # assumes an ``int`` result and silently truncates HWND/HDC/HBITMAP values.
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                                       ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    user32.CreateWindowExW.restype = ctypes.c_void_p
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = wintypes.WORD
    user32.DefWindowProcW.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.PostMessageW.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostThreadMessageW.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), ctypes.c_void_p, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = ctypes.c_int
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.GetDC.argtypes = [ctypes.c_void_p]
    user32.GetDC.restype = ctypes.c_void_p
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.UpdateLayeredWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(POINT),
                                           ctypes.POINTER(SIZE), ctypes.c_void_p, ctypes.POINTER(POINT),
                                           wintypes.DWORD, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
    user32.UpdateLayeredWindow.restype = wintypes.BOOL
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, wintypes.DWORD]
    gdi32.CreateDIBSection.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    gdi32.CreatePen.restype = ctypes.c_void_p
    gdi32.GetStockObject.argtypes = [ctypes.c_int]
    gdi32.GetStockObject.restype = ctypes.c_void_p
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.SetBkMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
    gdi32.SetBkMode.restype = ctypes.c_int
    gdi32.SetTextColor.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    gdi32.SetTextColor.restype = wintypes.DWORD
    gdi32.Rectangle.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    gdi32.Rectangle.restype = wintypes.BOOL
    gdi32.MoveToEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(POINT)]
    gdi32.MoveToEx.restype = wintypes.BOOL
    gdi32.LineTo.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    gdi32.LineTo.restype = wintypes.BOOL
    gdi32.CreateFontW.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPCWSTR]
    gdi32.CreateFontW.restype = ctypes.c_void_p
    gdi32.TextOutW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int]
    gdi32.TextOutW.restype = wintypes.BOOL
    gdi32.GetTextExtentPoint32W.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_int,
                                            ctypes.POINTER(SIZE)]
    gdi32.GetTextExtentPoint32W.restype = wintypes.BOOL
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    _instances: dict[int, "Win32GdiOverlay"] = {}
    _class_lock = threading.Lock()
    _class_registered = False
    _window_class_name = "ok-script.Win32GdiOverlay"


def _rgb(red, green, blue):
    return red | (green << 8) | (blue << 16)


class GdiCanvas:
    """Small custom-draw surface shared by non-Qt callers."""

    def __init__(self, hdc, ratio):
        self.hdc = hdc
        self.ratio = ratio

    def rectangle(self, x, y, width, height, color=(255, 0, 0), line_width=2):
        if os.name != "nt":
            return
        pen = gdi32.CreatePen(PS_SOLID, max(1, int(line_width * self.ratio)), _rgb(*color))
        old_pen = gdi32.SelectObject(self.hdc, pen)
        old_brush = gdi32.SelectObject(self.hdc, gdi32.GetStockObject(5))  # NULL_BRUSH
        gdi32.Rectangle(self.hdc, int(x * self.ratio), int(y * self.ratio),
                        int((x + width) * self.ratio), int((y + height) * self.ratio))
        gdi32.SelectObject(self.hdc, old_pen)
        gdi32.SelectObject(self.hdc, old_brush)
        gdi32.DeleteObject(pen)

    def text(self, x, y, value, color=(255, 255, 255)):
        if os.name != "nt":
            return
        gdi32.SetTextColor(self.hdc, _rgb(*color))
        gdi32.TextOutW(self.hdc, int(x * self.ratio), int(y * self.ratio), str(value), len(str(value)))


class Win32GdiOverlay:
    """Native overlay with the API previously exposed by ``OverlayWindow``."""

    def __init__(self, hwnd_window=None, *, native=True, exit_event=None):
        self._lock = threading.RLock()
        self._ready = threading.Event()
        self._close_lock = threading.Lock()
        self._closed = False
        self.exit_event = exit_event or ExitEvent()
        if hasattr(self.exit_event, "bind_stop"):
            self.exit_event.bind_stop(self)
        self._hwnd = 0
        self._window_thread_id = 0
        self._owner_hwnd = int(getattr(hwnd_window, "hwnd", 0) or 0)
        self._render_posted = False
        self._last_overlay_state = None
        self._last_painted_state = None
        self._last_native_state = None
        self._last_draw_log_at = 0.0
        # ``native=False`` is useful for unit tests and non-desktop hosts.
        self._native_available = os.name == "nt" and native
        self._source_visible = False
        self._visible = False
        self._x = self._y = self._width = self._height = 0
        self._frame_width = self._frame_height = 0
        self._boxes_enabled = self._config_value("use_overlay", False)
        self._boxes_active = False
        self._boxes_until = 0.0
        self._custom_active_until = 0.0
        self._mouse_position = (0, 0)
        self._pointer_inside = False
        self._is_alt_down = False
        self._right_down = False
        self._accumulated_coords = []
        self._click_points = []
        self._input_stop = threading.Event()
        self._input_thread = None
        self._expiry_lock = threading.RLock()
        self._expiry_jobs = {}
        self._expiry_wakeup_at = None
        self._expiry_handler = Handler(
            self.exit_event, "Win32GdiOverlayExpiry", daemon=True)
        self._qt_clipboard_writer = self._create_qt_clipboard_writer()
        self.custom_painters = {}
        self._custom_painter_until = {}
        self.blur_images = []
        self._py_object = ctypes.py_object(self) if self._native_available else None

        communicate.draw_box.connect(self.on_draw_box)
        communicate.clear_box.connect(self.clear_drawing)
        communicate.blur_overlay.connect(self.update_blur_patches)
        communicate.clear_blur_overlay.connect(self.clear_blur_overlay)

        if self._native_available:
            self._thread = threading.Thread(target=self._window_thread, name="Win32GdiOverlay", daemon=True)
            self._thread.start()
            self._ready.wait(2)
            if self._hwnd:
                self._input_thread = threading.Thread(
                    target=self._input_loop, name="Win32GdiOverlayInput", daemon=True)
                self._input_thread.start()
        logger.info(
            f"Win32 overlay initialized: native={self._native_available}, hwnd={self._hwnd}, "
            f"owner={self._owner_hwnd}")

        if hwnd_window is not None:
            self.sync_source_window(hwnd_window)

    @staticmethod
    def _config_value(name, default):
        app = getattr(og, "app", None)
        config = getattr(app, "ok_config", None)
        return config.get(name, default) if config is not None else default

    def _seed_source_window(self, hwnd_window):
        origin = getattr(hwnd_window, "get_capture_origin", None)
        if callable(origin):
            x, y = origin()
        else:
            x = getattr(hwnd_window, "x", 0) + getattr(hwnd_window, "real_x_offset", 0)
            y = getattr(hwnd_window, "y", 0) + getattr(hwnd_window, "real_y_offset", 0)
        self.update_overlay(bool(getattr(hwnd_window, "visible", False)), x, y,
                            getattr(hwnd_window, "window_width", 0), getattr(hwnd_window, "window_height", 0),
                            getattr(hwnd_window, "width", 0), getattr(hwnd_window, "height", 0),
                            getattr(hwnd_window, "scaling", 1.0) or 1.0)

    def sync_source_window(self, hwnd_window=None):
        """Seed geometry and visibility from the latest capture window state."""
        if hwnd_window is None:
            device_manager = getattr(og, "device_manager", None)
            hwnd_window = getattr(device_manager, "hwnd_window", None)
        if hwnd_window is not None:
            self._seed_source_window(hwnd_window)

    def update_overlay(self, visible, x, y, _window_width, _window_height, width, height, _scaling):
        with self._lock:
            self._source_visible = bool(visible)
            # Win32 accepts physical pixels. Qt previously scaled its widget
            # geometry because QWidget coordinates are device-independent.
            self._x, self._y = int(x), int(y)
            self._width, self._height = max(0, int(width)), max(0, int(height))
            self._frame_width, self._frame_height = self._width, self._height
            if not visible:
                self.blur_images = []
                self._reset_coordinate_capture()
            state = (self._source_visible, self._x, self._y, self._width, self._height)
            if state != self._last_overlay_state:
                self._last_overlay_state = state
                logger.info(
                    f"Win32 overlay source: visible={self._source_visible}, "
                    f"rect=({self._x},{self._y},{self._width}x{self._height}), "
                    f"boxes_enabled={self._boxes_enabled}")
        self._schedule_render()

    def set_boxes_enabled(self, enabled):
        with self._lock:
            self._boxes_enabled = bool(enabled)
            if not enabled:
                self._boxes_active = False
                self._boxes_until = 0
                self._reset_coordinate_capture()
            logger.info(
                f"Win32 overlay boxes enabled={self._boxes_enabled}, "
                f"source_visible={self._source_visible}, hwnd={self._hwnd}")
        if not enabled:
            self._cancel_expiry("boxes")
        self._schedule_render()

    def request_show(self, duration=4.0):
        with self._lock:
            self._custom_active_until = time.monotonic() + max(0, float(duration))
        self._schedule_expiry("custom-active", duration, self.expire_custom_drawing)
        self._schedule_render()

    def draw(self, key, callback, duration=None):
        if not callable(callback):
            raise TypeError("callback must be callable")
        expires_at = None
        with self._lock:
            self.custom_painters[str(key)] = callback
            if duration is None:
                self._custom_painter_until.pop(str(key), None)
            else:
                expires_at = time.monotonic() + max(0, float(duration))
                self._custom_painter_until[str(key)] = expires_at
        if duration is not None:
            self._schedule_expiry(
                f"custom:{key}", duration,
                lambda: self._expire_custom_draw(str(key), expires_at))
        else:
            self._cancel_expiry(f"custom:{key}")
        self._schedule_render()

    def clear_draw(self, key=None):
        with self._lock:
            if key is None:
                self.custom_painters.clear()
                self._custom_painter_until.clear()
            else:
                self.custom_painters.pop(str(key), None)
                self._custom_painter_until.pop(str(key), None)
        if key is None:
            self._cancel_expiry(prefix="custom:")
        else:
            self._cancel_expiry(f"custom:{key}")
        self._schedule_render()

    def on_draw_box(self, _key, boxes, _color, _frame, _debug):
        if boxes and self._boxes_enabled:
            now = time.monotonic()
            with self._lock:
                self._boxes_active = True
                self._boxes_until = now + 4.0
                if now - self._last_draw_log_at > 1.0:
                    self._last_draw_log_at = now
                    # logger.info(
                    #     f"Win32 overlay draw event: key={_key}, boxes={len(boxes) if hasattr(boxes, '__len__') else 1}, "
                    #     f"source_visible={self._source_visible}, rect={self._width}x{self._height}")
            self._schedule_expiry("boxes", 4.01, self.expire_boxes)
            self._schedule_render()

    def clear_drawing(self):
        with self._lock:
            self._boxes_active = False
            self._boxes_until = 0
        self._cancel_expiry("boxes")
        self._schedule_render()

    def expire_boxes(self):
        with self._lock:
            if time.monotonic() < self._boxes_until:
                return
            self._boxes_active = False
        self._schedule_render()

    def expire_custom_drawing(self):
        with self._lock:
            if time.monotonic() < self._custom_active_until:
                return
            self._custom_active_until = 0
        self._schedule_render()

    def _expire_custom_draw(self, key, expected_until=None):
        with self._lock:
            until = self._custom_painter_until.get(key)
            if until is None or (expected_until is not None and until != expected_until):
                return
            if time.monotonic() < until:
                return
            self.custom_painters.pop(key, None)
            self._custom_painter_until.pop(key, None)
        self._schedule_render()

    def update_blur_patches(self, patches):
        with self._lock:
            self.blur_images = list(patches or [])
        self._schedule_render()

    def clear_blur_overlay(self):
        self.clear_blur_patches()

    def clear_blur_patches(self):
        with self._lock:
            self.blur_images = []
        self._schedule_render()

    def isVisible(self):
        return self._visible

    def show(self):
        with self._lock:
            self._source_visible = True
            self._boxes_enabled = True
        self._schedule_render()

    def hide(self):
        with self._lock:
            self._source_visible = False
        self._schedule_render()

    def close(self, wait=True):
        """Signal shutdown, optionally waiting outside ExitEvent callbacks."""
        with self._close_lock:
            first_close = not self._closed
            self._closed = True
        if first_close:
            for signal, callback in (
                    (communicate.draw_box, self.on_draw_box),
                    (communicate.clear_box, self.clear_drawing),
                    (communicate.blur_overlay, self.update_blur_patches),
                    (communicate.clear_blur_overlay, self.clear_blur_overlay)):
                signal.disconnect(callback)
            communicate.window.disconnect(self.update_overlay)
            self._input_stop.set()
            with self._expiry_lock:
                self._expiry_jobs.clear()
                self._expiry_wakeup_at = None
            self._expiry_handler.stop()
            if hasattr(self.exit_event, "unbind_stop"):
                self.exit_event.unbind_stop(self)
            if self._native_available:
                if self._hwnd:
                    user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
                if self._window_thread_id:
                    # WM_QUIT guarantees GetMessageW returns even if window
                    # destruction races with an in-progress layered render.
                    user32.PostThreadMessageW(self._window_thread_id, WM_QUIT, 0, 0)
        if wait:
            self._join_workers(timeout=.5)

    def _join_workers(self, timeout):
        deadline = time.monotonic() + max(0, timeout)
        for thread in (self._input_thread, self._expiry_handler.thread,
                       getattr(self, "_thread", None)):
            if thread is None or thread is threading.current_thread() or not thread.is_alive():
                continue
            thread.join(max(0, deadline - time.monotonic()))

    def stop(self):
        """Non-blocking ExitEvent callback; never stall the GUI close event."""
        self.close(wait=False)

    @staticmethod
    def _create_qt_clipboard_writer():
        """Create the legacy Qt clipboard bridge when a Qt app is active."""
        try:
            from PySide6.QtCore import QObject, Qt, Signal
            from PySide6.QtGui import QGuiApplication

            app = QGuiApplication.instance()
            if app is None:
                return None

            class ClipboardWriter(QObject):
                requested = Signal(str)

                def __init__(self):
                    super().__init__()
                    self.requested.connect(
                        lambda value: QGuiApplication.clipboard().setText(value),
                        Qt.QueuedConnection,
                    )

            writer = ClipboardWriter()
            writer.moveToThread(app.thread())
            return writer
        except (ImportError, RuntimeError):
            return None

    def _reset_coordinate_capture(self):
        self._is_alt_down = False
        self._right_down = False
        self._pointer_inside = False
        self._accumulated_coords = []
        self._click_points = []

    def _poll_input(self):
        """Poll global input because the overlay remains click-through."""
        point = POINT()
        if not user32.GetCursorPos(ctypes.byref(point)):
            return
        right_state = user32.GetAsyncKeyState(VK_RBUTTON)
        self._update_input_state(
            bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000),
            bool(right_state & 0x8000 or right_state & 0x0001),
            point.x,
            point.y,
        )

    def _input_loop(self):
        """Poll independently so layered-window painting cannot miss clicks."""
        while not self._input_stop.is_set() and not self.exit_event.is_set():
            try:
                self._poll_input()
            except Exception as error:
                logger.warning(f"overlay input polling failed: {error}")
            self._input_stop.wait(INPUT_POLL_INTERVAL)

    def _update_input_state(self, alt_down, right_down, cursor_x, cursor_y):
        """Update crosshair/copy state from one input sample.

        Kept separate from the Win32 polling call so the interaction can be
        verified without creating a native desktop window.
        """
        clipboard_text = None
        with self._lock:
            if not self._boxes_enabled:
                alt_down = False
                right_down = False
            previous = (self._is_alt_down, self._right_down, self._pointer_inside,
                        self._mouse_position, tuple(self._click_points))
            relative = (int(cursor_x) - self._x, int(cursor_y) - self._y)
            inside = (self._source_visible and 0 <= relative[0] < self._width
                      and 0 <= relative[1] < self._height)

            if not alt_down:
                self._accumulated_coords = []
                self._click_points = []
            if inside:
                self._mouse_position = relative

            # Capture only the up-to-down edge. The click still passes through
            # to the game because the native window has WS_EX_TRANSPARENT.
            if alt_down and right_down and not self._right_down and inside and self._width and self._height:
                x_percent = relative[0] / self._width
                y_percent = relative[1] / self._height
                coordinate = f"{x_percent:.3f}, {y_percent:.3f}"
                if len(self._accumulated_coords) >= 2:
                    self._accumulated_coords[1] = coordinate
                    self._click_points[1] = relative
                else:
                    self._accumulated_coords.append(coordinate)
                    self._click_points.append(relative)
                clipboard_text = ", ".join(self._accumulated_coords)

            self._is_alt_down = bool(alt_down)
            self._right_down = bool(right_down)
            self._pointer_inside = inside
            current = (self._is_alt_down, self._right_down, self._pointer_inside,
                       self._mouse_position, tuple(self._click_points))

        if clipboard_text is not None:
            self._copy_to_clipboard(clipboard_text)
        if current != previous:
            self._schedule_render()

    def _copy_to_clipboard(self, text):
        try:
            if self._qt_clipboard_writer is not None:
                # This reproduces the pre-refactor QGuiApplication clipboard
                # path without touching Qt from the native polling thread.
                self._qt_clipboard_writer.requested.emit(text)
                return
            from ok.third_party.paperclip import copy
            copy(text)
        except Exception as error:
            logger.warning(f"coordinate clipboard copy failed: {error}")

    def _schedule_expiry(self, key, duration, callback):
        """Replace one keyed deadline without creating a thread per event.

        The boxes job is updated hundreds of times per second during busy
        scenes, but this mapping remains bounded to one entry for that job.
        """
        deadline = time.monotonic() + max(0, float(duration)) + .01
        with self._expiry_lock:
            if self._closed or self.exit_event.is_set():
                return
            self._expiry_jobs[str(key)] = (deadline, callback)
            self._queue_next_expiry_locked()

    def _cancel_expiry(self, key=None, prefix=None):
        with self._expiry_lock:
            if key is not None:
                self._expiry_jobs.pop(str(key), None)
            elif prefix is not None:
                matches = [job_key for job_key in self._expiry_jobs if job_key.startswith(prefix)]
                for job_key in matches:
                    self._expiry_jobs.pop(job_key, None)
            else:
                self._expiry_jobs.clear()

    def _queue_next_expiry_locked(self):
        if not self._expiry_jobs:
            return
        deadline = min(job[0] for job in self._expiry_jobs.values())
        # An already queued earlier wake-up is harmless and avoids touching
        # Handler's queue for every boxes event that merely extends a deadline.
        if self._expiry_wakeup_at is not None and self._expiry_wakeup_at <= deadline:
            return
        self._expiry_wakeup_at = deadline
        self._expiry_handler.post(
            self._process_expiries, delay=max(0, deadline - time.monotonic()),
            remove_existing=True)

    def _process_expiries(self):
        callbacks = []
        with self._expiry_lock:
            self._expiry_wakeup_at = None
            now = time.monotonic()
            for key, (deadline, callback) in tuple(self._expiry_jobs.items()):
                if deadline <= now:
                    self._expiry_jobs.pop(key, None)
                    callbacks.append((key, callback))
            self._queue_next_expiry_locked()
        for key, callback in callbacks:
            try:
                callback()
            except Exception as error:
                logger.warning(f"overlay expiry callback failed for {key}: {error}")

    def _schedule_render(self):
        if not self._native_available or not self._hwnd or self._closed:
            self._visible = self._required_visible()
            return
        with self._lock:
            if self._render_posted:
                return
            self._render_posted = True
        user32.PostMessageW(self._hwnd, WM_RENDER, 0, 0)

    def _required_visible(self):
        with self._lock:
            if self._closed:
                return False
            custom_active = self._custom_active_until > time.monotonic()
            # Match the Qt overlay's foreground contract: never leave any
            # overlay content over another application when the game loses
            # focus, including freshly received background draw events.
            return bool(self._source_visible and
                        (
                                    self._boxes_enabled or self._boxes_active or custom_active or self.blur_images or
                                    self.custom_painters or (self._is_alt_down and self._pointer_inside)))

    def _window_thread(self):
        self._window_thread_id = kernel32.GetCurrentThreadId()
        try:
            self._register_class()
            instance = kernel32.GetModuleHandleW(None)
            param = ctypes.cast(ctypes.pointer(self._py_object), ctypes.c_void_p)
            hwnd = user32.CreateWindowExW(
                WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                _window_class_name, None, WS_POPUP, 0, 0, 0, 0, self._owner_hwnd or None, None, instance, param,
            )
            if not hwnd:
                logger.error(f"CreateWindowExW failed for overlay: {ctypes.get_last_error()}")
                return
            self._hwnd = hwnd
            logger.info(f"Win32 overlay native window created: hwnd={hwnd}, owner={self._owner_hwnd}")
        except Exception as error:
            logger.error(f"Win32 overlay startup failed: {error}")
        finally:
            self._ready.set()
        if not self._hwnd:
            return
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        self._hwnd = 0

    @staticmethod
    def _register_class():
        global _class_registered
        with _class_lock:
            if _class_registered:
                return
            instance = kernel32.GetModuleHandleW(None)
            window_class = WNDCLASSW()
            window_class.lpfnWndProc = _wnd_proc
            window_class.hInstance = instance
            window_class.lpszClassName = _window_class_name
            result = user32.RegisterClassW(ctypes.byref(window_class))
            if not result and ctypes.get_last_error() != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                raise ctypes.WinError(ctypes.get_last_error())
            _class_registered = True

    def _render(self):
        with self._lock:
            self._render_posted = False
        if not self._required_visible() or self._width <= 0 or self._height <= 0:
            user32.ShowWindow(self._hwnd, SW_HIDE)
            self._visible = False
            return
        try:
            self._paint_layered_window()
            self._visible = True
            painted_state = (self._source_visible, self._width, self._height, self._boxes_enabled, self._boxes_active)
            if painted_state != self._last_painted_state:
                self._last_painted_state = painted_state
                logger.info(
                    f"Win32 overlay presented: rect=({self._x},{self._y},{self._width}x{self._height}), "
                    f"boxes_enabled={self._boxes_enabled}, boxes_active={self._boxes_active}")
        except Exception as error:
            logger.error(f"Win32 overlay render failed: {error}")

    def _paint_layered_window(self):
        import numpy as np

        width, height = self._width, self._height
        screen_dc = user32.GetDC(None)
        memory_dc = gdi32.CreateCompatibleDC(screen_dc)
        bits = ctypes.c_void_p()
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height  # top-down BGRA
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB
        bitmap = gdi32.CreateDIBSection(memory_dc, ctypes.byref(info), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
        old_bitmap = gdi32.SelectObject(memory_dc, bitmap)
        try:
            buffer = np.ctypeslib.as_array(ctypes.cast(bits, ctypes.POINTER(ctypes.c_ubyte)),
                                           shape=(height * width * 4,))
            pixels = buffer.reshape((height, width, 4))
            pixels.fill(0)
            self._paint_blur_pixels(pixels)
            gdi32.SetBkMode(memory_dc, TRANSPARENT)
            self._paint_border(memory_dc)
            self._paint_boxes(memory_dc)
            self._paint_coordinate_overlay(memory_dc, pixels)
            self._paint_custom(memory_dc)
            # GDI leaves alpha untouched.  Every coloured pixel becomes opaque;
            # untouched pixels stay transparent in the layered window.
            pixels[:, :, 3] = np.where(np.any(pixels[:, :, :3] != 0, axis=2), 255, pixels[:, :, 3])
            destination = POINT(self._x, self._y)
            source = POINT(0, 0)
            size = SIZE(width, height)
            blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
            # Establish topmost placement before presenting the DIB.  This is
            # also checked explicitly: a silent SetWindowPos failure leaves a
            # perfectly rendered layered window behind the game.
            if not user32.SetWindowPos(self._hwnd, HWND_TOPMOST, self._x, self._y, width, height,
                                       SWP_NOACTIVATE | SWP_SHOWWINDOW):
                raise ctypes.WinError(ctypes.get_last_error())
            if not user32.UpdateLayeredWindow(self._hwnd, screen_dc, ctypes.byref(destination), ctypes.byref(size),
                                              memory_dc,
                                              ctypes.byref(source), 0, ctypes.byref(blend), 2):
                raise ctypes.WinError(ctypes.get_last_error())
            # A source-window update can arrive while GDI is drawing. Do not
            # re-show a completed frame after that update declared the game
            # background.
            if not self._required_visible():
                user32.ShowWindow(self._hwnd, SW_HIDE)
                self._visible = False
                return
            user32.ShowWindow(self._hwnd, SW_SHOWNOACTIVATE)
            rect = RECT()
            user32.GetWindowRect(self._hwnd, ctypes.byref(rect))
            native_state = (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top,
                            bool(user32.IsWindowVisible(self._hwnd)))
            if native_state != self._last_native_state:
                self._last_native_state = native_state
                logger.info(f"Win32 overlay native placement: rect={native_state[:4]}, visible={native_state[4]}")
        finally:
            gdi32.SelectObject(memory_dc, old_bitmap)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(memory_dc)
            user32.ReleaseDC(None, screen_dc)

    def _ratio(self):
        return self._width / self._frame_width if self._frame_width else 1.0

    def _paint_blur_pixels(self, pixels):
        if not self.blur_images:
            return
        try:
            import cv2
        except ImportError:
            return
        ratio = self._ratio()
        for x, y, width, height, patch in self.blur_images:
            if patch is None or getattr(patch, "size", 0) == 0:
                continue
            target_width, target_height = max(1, round(width * ratio)), max(1, round(height * ratio))
            image = patch
            if image.shape[1] != target_width or image.shape[0] != target_height:
                image = cv2.resize(image, (target_width, target_height))
            left, top = max(0, round(x * ratio)), max(0, round(y * ratio))
            right, bottom = min(self._width, left + target_width), min(self._height, top + target_height)
            if right <= left or bottom <= top:
                continue
            pixels[top:bottom, left:right, :3] = image[:bottom - top, :right - left, :3]
            pixels[top:bottom, left:right, 3] = 255

    def _paint_boxes(self, hdc):
        if not (self._boxes_enabled and self._boxes_active):
            return
        ratio = self._ratio()
        screenshot = getattr(getattr(og, "ok", None), "screenshot", None)
        # Feature detection updates this dictionary on the task thread while
        # this method runs on the native window thread. Retry a small snapshot
        # rather than iterating the live mapping and dropping the whole frame.
        ui_dict = getattr(screenshot, "ui_dict", {})
        items = ()
        for _ in range(3):
            try:
                items = tuple(ui_dict.items())
                break
            except RuntimeError:
                continue
        for key, value in items:
            boxes, _timestamp, color = value
            red, green, blue = tuple(color)[:3]
            pen = gdi32.CreatePen(PS_SOLID, max(1, round(2 * ratio)), _rgb(red, green, blue))
            old_pen = gdi32.SelectObject(hdc, pen)
            old_brush = gdi32.SelectObject(hdc, gdi32.GetStockObject(5))
            gdi32.SetTextColor(hdc, _rgb(red, green, blue))
            for box in boxes:
                left, top = round(box.x * ratio), round(box.y * ratio)
                right, bottom = round((box.x + box.width) * ratio), round((box.y + box.height) * ratio)
                gdi32.Rectangle(hdc, left, top, right, bottom)
                label = f"{box.name or key}_{round(box.confidence * 100)}"
                gdi32.TextOutW(hdc, left, bottom + 3, label, len(label))
            gdi32.SelectObject(hdc, old_pen)
            gdi32.SelectObject(hdc, old_brush)
            gdi32.DeleteObject(pen)

    def _paint_border(self, hdc):
        """Match the Qt overlay's visible enabled-state frame.

        A layered window with only transparent pixels is technically shown but
        cannot be seen.  The legacy QWidget drew its border whenever overlay
        boxes were enabled, even before the first feature was detected.
        """
        if not self._boxes_enabled:
            return
        pen = gdi32.CreatePen(PS_SOLID, 2, _rgb(239, 160, 239))
        old_pen = gdi32.SelectObject(hdc, pen)
        old_brush = gdi32.SelectObject(hdc, gdi32.GetStockObject(5))
        gdi32.Rectangle(hdc, 0, 0, max(1, self._width - 1), max(1, self._height - 1))
        gdi32.SelectObject(hdc, old_pen)
        gdi32.SelectObject(hdc, old_brush)
        gdi32.DeleteObject(pen)

    @staticmethod
    def _paint_dark_panel(pixels, left, top, right, bottom, alpha=180):
        """Paint clipped translucent black without becoming opaque later.

        The compositor promotes non-black GDI pixels to full alpha. Keeping
        the panel RGB at zero preserves the requested alpha while subsequent
        text drawing remains crisp and opaque.
        """
        height, width = pixels.shape[:2]
        left, top = max(0, int(left)), max(0, int(top))
        right, bottom = min(width, int(right)), min(height, int(bottom))
        if right <= left or bottom <= top:
            return
        panel = pixels[top:bottom, left:right]
        panel[:, :, :3] = 0
        panel[:, :, 3] = max(0, min(255, int(alpha)))

    @staticmethod
    def _text_extent(hdc, text, fallback_width=8, fallback_height=16):
        size = SIZE()
        if gdi32.GetTextExtentPoint32W(hdc, text, len(text), ctypes.byref(size)):
            return max(1, size.cx), max(1, size.cy)
        return max(1, len(text) * fallback_width), fallback_height

    def _paint_coordinate_overlay(self, hdc, pixels):
        if not (self._is_alt_down and self._pointer_inside):
            return
        mouse_x, mouse_y = self._mouse_position
        pen = gdi32.CreatePen(PS_DASH, 1, _rgb(0, 255, 0))
        old_pen = gdi32.SelectObject(hdc, pen)
        gdi32.MoveToEx(hdc, 0, mouse_y, None)
        gdi32.LineTo(hdc, self._width, mouse_y)
        gdi32.MoveToEx(hdc, mouse_x, 0, None)
        gdi32.LineTo(hdc, mouse_x, self._height)
        gdi32.SelectObject(hdc, old_pen)
        gdi32.DeleteObject(pen)

        marker_pen = gdi32.CreatePen(PS_SOLID, 2, _rgb(255, 0, 0))
        old_pen = gdi32.SelectObject(hdc, marker_pen)
        old_brush = gdi32.SelectObject(hdc, gdi32.GetStockObject(5))
        if len(self._click_points) == 1:
            x, y = self._click_points[0]
            gdi32.MoveToEx(hdc, x - 5, y, None)
            gdi32.LineTo(hdc, x + 6, y)
            gdi32.MoveToEx(hdc, x, y - 5, None)
            gdi32.LineTo(hdc, x, y + 6)
        elif len(self._click_points) >= 2:
            (x1, y1), (x2, y2) = self._click_points[:2]
            gdi32.Rectangle(hdc, min(x1, x2), min(y1, y2), max(x1, x2) + 1, max(y1, y2) + 1)
        gdi32.SelectObject(hdc, old_pen)
        gdi32.SelectObject(hdc, old_brush)
        gdi32.DeleteObject(marker_pen)

        x_percent = mouse_x / self._width if self._width else 0
        y_percent = mouse_y / self._height if self._height else 0
        device_manager = getattr(og, "device_manager", None)
        device_width = getattr(device_manager, "width", 0) or self._width
        device_height = getattr(device_manager, "height", 0) or self._height
        device_x = int(x_percent * device_width)
        device_y = int(y_percent * device_height)
        text = (f"{device_x}, {device_y}, {x_percent:.3f}, {y_percent:.3f} "
                f"(Alt+right click to copy)")
        font = gdi32.CreateFontW(-24, 0, 0, 0, 600, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")
        old_font = gdi32.SelectObject(hdc, font)
        text_width, text_height = self._text_extent(
            hdc, text, fallback_width=13, fallback_height=28)
        self._paint_dark_panel(
            pixels, 8, 10, min(self._width, 16 + text_width + 8),
            min(self._height, 16 + text_height + 6))
        gdi32.SetTextColor(hdc, _rgb(255, 85, 85))
        gdi32.TextOutW(hdc, 16, 16, text, len(text))
        gdi32.SelectObject(hdc, old_font)
        gdi32.DeleteObject(font)

    def _paint_custom(self, hdc):
        canvas = GdiCanvas(hdc, self._ratio())
        with self._lock:
            painters = list(self.custom_painters.items())
        for key, callback in painters:
            try:
                callback(canvas, self)
            except Exception as error:
                logger.warning(f"custom overlay painter {key} failed: {error}")


if os.name == "nt":
    @WNDPROC
    def _wnd_proc(hwnd, message, wparam, lparam):
        if message == WM_NCCREATE:
            create = ctypes.cast(lparam, ctypes.POINTER(CREATESTRUCTW)).contents
            instance = ctypes.cast(create.lpCreateParams, ctypes.POINTER(ctypes.py_object)).contents.value
            _instances[hwnd] = instance
        instance = _instances.get(hwnd)
        if instance is not None and message == WM_RENDER:
            instance._render()
            return 0
        if message == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if message == WM_DESTROY:
            _instances.pop(hwnd, None)
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)
else:
    _wnd_proc = None
