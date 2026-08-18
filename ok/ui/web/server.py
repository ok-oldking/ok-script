import ctypes
import logging
import os
import socket
import threading
import webbrowser

from ok.util.logger import Logger
from ok.core.ui_config import resolve_window_size
from ok.ui.web.requirements import check_web_requirements

logger = Logger.get_logger("web_server")

_WINDOW_CORNER_RADIUS = 16
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2
_HTLEFT, _HTRIGHT, _HTTOP, _HTTOPLEFT = 10, 11, 12, 13
_HTTOPRIGHT, _HTBOTTOM, _HTBOTTOMLEFT, _HTBOTTOMRIGHT = 14, 15, 16, 17
_SWP_NOZORDER_NOACTIVATE = 0x0004 | 0x0010
_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_LWA_ALPHA = 0x00000002


class _WindowRect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def _resize_bounds(bounds, hit_test, dx, dy, min_width, min_height):
    """Return resized screen bounds for a native edge or corner drag."""
    left, top, right, bottom = bounds
    if hit_test in (_HTLEFT, _HTTOPLEFT, _HTBOTTOMLEFT):
        left = min(left + dx, right - min_width)
    if hit_test in (_HTRIGHT, _HTTOPRIGHT, _HTBOTTOMRIGHT):
        right = max(right + dx, left + min_width)
    if hit_test in (_HTTOP, _HTTOPLEFT, _HTTOPRIGHT):
        top = min(top + dy, bottom - min_height)
    if hit_test in (_HTBOTTOM, _HTBOTTOMLEFT, _HTBOTTOMRIGHT):
        bottom = max(bottom + dy, top + min_height)
    return left, top, right - left, bottom - top


def _make_resize_handle_transparent(control):
    """Hide a native resize overlay without making its hit area click-through."""
    if os.name != "nt":
        return False
    user32 = ctypes.windll.user32
    user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetLayeredWindowAttributes.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_ubyte, ctypes.c_uint32,
    ]
    user32.SetLayeredWindowAttributes.restype = ctypes.c_bool

    hwnd = control.Handle.ToInt64()
    extended_style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, extended_style | _WS_EX_LAYERED)
    # Alpha zero is click-through; one is visually imperceptible but keeps input.
    return bool(user32.SetLayeredWindowAttributes(hwnd, 0, 1, _LWA_ALPHA))


def _install_native_resize_handles(window, rounded_region):
    """Overlay native edge controls so WebView2 cannot consume resize input."""
    if os.name != "nt":
        return False
    native_window = getattr(window, "native", None)
    if native_window is None:
        return False
    if getattr(native_window, "InvokeRequired", False):
        from System import Action

        installed = []
        native_window.Invoke(Action(lambda: installed.append(
            _install_native_resize_handles(window, rounded_region)
        )))
        return bool(installed and installed[0])
    if getattr(native_window, "_ok_resize_handles", None):
        return True

    from System.Windows.Forms import (
        AnchorStyles, Cursor, Cursors, MouseButtons, Panel
    )

    width = native_window.ClientSize.Width
    height = native_window.ClientSize.Height
    edge, corner = 6, 18
    specs = (
        (edge, 0, width - edge * 2, edge, Cursors.SizeNS, _HTTOP,
         AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right),
        (width - edge, corner, edge, height - corner * 2, Cursors.SizeWE,
         _HTRIGHT, AnchorStyles.Top | AnchorStyles.Right | AnchorStyles.Bottom),
        (edge, height - edge, width - edge * 2, edge, Cursors.SizeNS,
         _HTBOTTOM, AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Bottom),
        (0, corner, edge, height - corner * 2, Cursors.SizeWE, _HTLEFT,
         AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Bottom),
        (0, 0, corner, corner, Cursors.SizeNWSE, _HTTOPLEFT,
         AnchorStyles.Top | AnchorStyles.Left),
        (width - corner, 0, corner, corner, Cursors.SizeNESW, _HTTOPRIGHT,
         AnchorStyles.Top | AnchorStyles.Right),
        (0, height - corner, corner, corner, Cursors.SizeNESW,
         _HTBOTTOMLEFT, AnchorStyles.Left | AnchorStyles.Bottom),
        (width - corner, height - corner, corner, corner, Cursors.SizeNWSE,
         _HTBOTTOMRIGHT, AnchorStyles.Right | AnchorStyles.Bottom),
    )
    hwnd = native_window.Handle.ToInt32()
    handles = []
    handlers = []
    resize_state = {}

    def update_rounded_region(_sender, _event):
        rounded_region.apply()

    native_window.Resize += update_rounded_region
    handlers.append(update_rounded_region)
    for x, y, panel_width, panel_height, cursor, hit_test, anchor in specs:
        panel = Panel()
        panel.SetBounds(x, y, max(1, panel_width), max(1, panel_height))
        panel.Anchor = anchor
        panel.Cursor = cursor
        panel.BackColor = native_window.BackColor

        def mouse_down(sender, event, hit=hit_test):
            if event.Button != MouseButtons.Left or ctypes.windll.user32.IsZoomed(hwnd):
                return
            position = Cursor.Position
            bounds = native_window.Bounds
            resize_state.clear()
            resize_state.update(
                hit=hit,
                cursor=(position.X, position.Y),
                bounds=(bounds.Left, bounds.Top, bounds.Right, bounds.Bottom),
                last_bounds=None,
            )
            sender.Capture = True

        def mouse_move(_sender, _event):
            if "hit" not in resize_state:
                return
            position = Cursor.Position
            start_x, start_y = resize_state["cursor"]
            next_bounds = _resize_bounds(
                resize_state["bounds"],
                resize_state["hit"],
                position.X - start_x,
                position.Y - start_y,
                native_window.MinimumSize.Width,
                native_window.MinimumSize.Height,
            )
            if next_bounds == resize_state["last_bounds"]:
                return
            resize_state["last_bounds"] = next_bounds
            left, top, width, height = next_bounds
            ctypes.windll.user32.SetWindowPos(
                hwnd,
                0,
                left,
                top,
                width,
                height,
                _SWP_NOZORDER_NOACTIVATE,
            )

        def mouse_up(sender, event):
            if event.Button == MouseButtons.Left:
                resize_state.clear()
                sender.Capture = False
                rounded_region.apply()

        def capture_changed(sender, _event):
            if not sender.Capture:
                resize_state.clear()

        panel.MouseDown += mouse_down
        panel.MouseMove += mouse_move
        panel.MouseUp += mouse_up
        panel.MouseCaptureChanged += capture_changed
        native_window.Controls.Add(panel)
        panel.BringToFront()
        _make_resize_handle_transparent(panel)
        handles.append(panel)
        handlers.extend((mouse_down, mouse_move, mouse_up, capture_changed))
    native_window._ok_resize_handles = (handles, handlers)
    return True


class _RoundedWindowRegion:
    """Clip a frameless Win32 window to DPI-aware rounded corners."""

    def __init__(self, window):
        self.window = window
        self._dwm_configured = False
        self._last_region_size = None

    def apply(self, *_):
        if os.name != "nt":
            return False
        native_window = getattr(self.window, "native", None)
        if native_window is None:
            return False
        hwnd = native_window.Handle.ToInt32()
        user32 = ctypes.windll.user32
        if not self._dwm_configured:
            user32.GetWindowRect.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(_WindowRect),
            ]
            user32.GetWindowRect.restype = ctypes.c_bool
            user32.SetWindowRgn.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_bool,
            ]
            ctypes.windll.gdi32.CreateRoundRectRgn.restype = ctypes.c_void_p
            corner_preference = ctypes.c_uint32(_DWMWCP_ROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                _DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(corner_preference),
                ctypes.sizeof(corner_preference),
            )
            self._dwm_configured = True
        if user32.IsZoomed(hwnd):
            user32.SetWindowRgn(hwnd, 0, True)
            self._last_region_size = None
            return True

        rect = _WindowRect()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        dpi = user32.GetDpiForWindow(hwnd) or 96
        region_size = (
            rect.right - rect.left,
            rect.bottom - rect.top,
            dpi,
        )
        if region_size == self._last_region_size:
            return True
        diameter = max(2, round(_WINDOW_CORNER_RADIUS * 2 * dpi / 96))
        region = ctypes.windll.gdi32.CreateRoundRectRgn(
            0,
            0,
            rect.right - rect.left + 1,
            rect.bottom - rect.top + 1,
            diameter,
            diameter,
        )
        if not region:
            return False
        self._last_region_size = region_size
        if not user32.SetWindowRgn(hwnd, region, True):
            self._last_region_size = None
            ctypes.windll.gdi32.DeleteObject(region)
            return False
        return True

    def clear(self, *_):
        native_window = getattr(self.window, "native", None)
        if os.name == "nt" and native_window is not None:
            ctypes.windll.user32.SetWindowRgn(
                native_window.Handle.ToInt32(), 0, True
            )
            self._last_region_size = None


def _saved_window_kwargs(window_config, ui_state):
    kwargs = {
        "width": window_config.get("width", 1200),
        "height": window_config.get("height", 800),
    }
    if not isinstance(ui_state, dict):
        return kwargs

    x = ui_state.get("window_x", -1)
    y = ui_state.get("window_y", -1)
    width = ui_state.get("window_width", -1)
    height = ui_state.get("window_height", -1)
    if x > 0 and y > 0 and width > 0 and height > 0:
        kwargs.update(
            x=x,
            y=y,
            width=width,
            height=height,
            maximized=bool(ui_state.get("window_maximized", False)),
        )
    return kwargs


class _WebviewGeometryState:
    """Persist pywebview geometry in the same _ok config used by Qt."""

    def __init__(self, ui_state, window=None):
        self.ui_state = ui_state
        self.window = window
        self.maximized = bool(ui_state.get("window_maximized", False))
        self.geometry = {
            "window_x": ui_state.get("window_x", -1),
            "window_y": ui_state.get("window_y", -1),
            "window_width": ui_state.get("window_width", -1),
            "window_height": ui_state.get("window_height", -1),
        }
        self._lock = threading.Lock()
        self._timer = None
        self._generation = 0

    def _native_is_maximized(self):
        native_window = getattr(self.window, "native", None)
        state = getattr(native_window, "WindowState", None)
        return str(state).endswith("Maximized") or state == 2

    def _record(self, **values):
        with self._lock:
            self.maximized = self._native_is_maximized()
            if not self.maximized:
                self.geometry.update(values)
            if self._timer is not None:
                self._timer.cancel()
            self._generation += 1
            generation = self._generation
            self._timer = threading.Timer(
                0.5,
                self._flush_if_current,
                args=(generation,),
            )
            self._timer.daemon = True
            self._timer.start()

    def _flush_if_current(self, generation):
        self._flush(generation)

    def moved(self, x, y):
        self._record(window_x=int(x), window_y=int(y))

    def resized(self, width, height):
        self._record(
            window_width=int(width),
            window_height=int(height),
        )

    def closing(self, window):
        with self._lock:
            self.maximized = self._native_is_maximized()
            if not self.maximized:
                self.geometry.update(
                    window_x=int(window.x),
                    window_y=int(window.y),
                    window_width=int(window.width),
                    window_height=int(window.height),
                )
        self.flush()

    def flush(self):
        self._flush()

    def _flush(self, expected_generation=None):
        with self._lock:
            if (expected_generation is not None
                    and expected_generation != self._generation):
                return
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._generation += 1
            values = dict(self.geometry)
            values["window_maximized"] = self.maximized

            changed = any(
                self.ui_state.get(key) != value
                for key, value in values.items()
            )
            if changed:
                dict.update(self.ui_state, values)
                save_file = getattr(self.ui_state, "save_file", None)
                if callable(save_file):
                    save_file()


def _move_winforms_window(native_window, x, y):
    """Move a pywebview WinForms window without passing None to SetWindowPos."""
    scale = native_window._scale
    x_physical = int(x * scale) if scale != 1 else int(x)
    y_physical = int(y * scale) if scale != 1 else int(y)
    ctypes.windll.user32.SetWindowPos(
        native_window.Handle.ToInt32(),
        0,
        x_physical,
        y_physical,
        0,
        0,
        0x0001 | 0x0004 | 0x0040,  # NOSIZE | NOZORDER | SHOWWINDOW
    )


def _patch_pywebview_winforms_move():
    """Work around pywebview 6.2.1 passing None for integer Win32 args."""
    if os.name != "nt":
        return False
    try:
        from webview.platforms import winforms
    except (ImportError, OSError):
        return False

    form_class = winforms.BrowserView.BrowserForm
    if form_class.move is not _move_winforms_window:
        form_class.move = _move_winforms_window
    return True


def _set_native_window_visible(window, visible):
    """Hide WinForms visually without suspending its WebView2 child."""
    native_window = getattr(window, "native", None)
    if os.name != "nt" or native_window is None:
        if visible:
            window.show()
        return False

    def apply_visibility():
        native_window.Opacity = 1 if visible else 0
        if visible:
            native_window.Show()
            native_window.Activate()

    if getattr(native_window, "InvokeRequired", False):
        from System import Action
        native_window.Invoke(Action(apply_visibility))
    else:
        apply_visibility()
    return True


class _WebviewWindowApi:
    """Window controls exposed only to the bundled pywebview client."""

    def __init__(self):
        # pywebview recursively serializes public js_api attributes. Keep the
        # native Window private or it will walk the WinForms/.NET object graph.
        self._window = None
        self.maximized = False
        self._revealed = False
        self._reveal_lock = threading.Lock()

    def _attach(self, window, maximized=False):
        self._window = window
        self.maximized = maximized

    def _on_maximized(self):
        self.maximized = True

    def _on_restored(self):
        self.maximized = False

    def _reveal(self):
        """Reveal the native window once React has completed its first layout."""
        with self._reveal_lock:
            if self._revealed or self._window is None:
                return False
            self._revealed = True
            window = self._window
        _set_native_window_visible(window, True)
        return True

    def minimize(self):
        if self._window is not None:
            self._window.minimize()

    def toggle_maximize(self):
        if self._window is None:
            return self.maximized
        if self.maximized:
            self._window.restore()
        else:
            self._window.maximize()
        self.maximized = not self.maximized
        return self.maximized

    def close(self):
        if self._window is not None:
            self._window.destroy()

class _OkServerLogHandler(logging.Handler):
    """Route ASGI server records through ok-script's logger."""

    _WEBSOCKET_FRAME_PREFIXES = (
        "> TEXT", "< TEXT", "> BINARY", "< BINARY",
        "> PING", "< PING", "> PONG", "< PONG",
        "> CLOSE", "< CLOSE",
    )

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.logger = Logger.get_logger("web_server")

    def emit(self, record):
        message = self.format(record)
        # Uvicorn sends WebSocket wire traces through uvicorn.error in debug
        # mode, while other backends use websockets.server. Filter by the
        # actual frame marker so neither path can feed streamed log events
        # back into the socket.
        if (record.levelno <= logging.DEBUG
                and message.lstrip().startswith(self._WEBSOCKET_FRAME_PREFIXES)):
            return
        if record.levelno <= logging.INFO:
            self.logger.debug(message)
        elif record.levelno <= logging.WARNING:
            self.logger.warning(message)
        elif record.levelno <= logging.ERROR:
            self.logger.error(message)
        else:
            self.logger.critical(message)


def _configure_server_logging():
    handler = _OkServerLogHandler()
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "websockets.server"):
        server_logger = logging.getLogger(name)
        server_logger.handlers = [handler]
        # websockets emits every inbound/outbound frame at DEBUG. Routing those
        # records through the app logger feeds log events back into the same
        # WebSocket and can create an endless stream of "> TEXT" messages.
        server_logger.setLevel(
            logging.INFO if name == "websockets.server" else logging.DEBUG
        )
        server_logger.propagate = False


def _run_webview(web_config, url, server, server_socket, ui_state=None,
                 ready_event=None):
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError(
            "Debug web UI requires pywebview. Install ok-script[web]."
        ) from exc

    window_config = resolve_window_size(web_config)
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
    _patch_pywebview_winforms_move()
    server_thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [server_socket]},
        name="web-server",
        daemon=True,
    )
    server_thread.start()
    window_api = None
    reveal_stop = threading.Event()
    try:
        saved_window = _saved_window_kwargs(window_config, ui_state)
        window_api = _WebviewWindowApi()
        window = webview.create_window(
            web_config.get("gui_title", "ok-script"),
            f"{url}?pywebview=1",
            js_api=window_api,
            min_size=(
                window_config.get("min_width", 800),
                window_config.get("min_height", 600),
            ),
            frameless=True,
            resizable=True,
            easy_drag=False,
            # pywebview's WinForms shadow path extends a 1px DWM frame into the
            # client area, leaving a colored line above our custom title bar.
            # Invisible client-area handles initiate the native resize loop.
            shadow=False,
            background_color="#251e22",
            **saved_window,
        )
        rounded_region = _RoundedWindowRegion(window)
        window_api._attach(window, saved_window.get("maximized", False))
        window.events.before_show += lambda: _set_native_window_visible(
            window, False
        )
        window.events.shown += rounded_region.apply
        window.events.shown += lambda: _install_native_resize_handles(
            window, rounded_region
        )
        def start_reveal_wait():
            def reveal_when_ready():
                if ready_event is not None:
                    ready_event.wait(15)
                if not reveal_stop.is_set():
                    window_api._reveal()

            threading.Thread(
                target=reveal_when_ready,
                name="webview-reveal",
                daemon=True,
            ).start()

        window.events.shown += start_reveal_wait
        window.events.maximized += window_api._on_maximized
        window.events.maximized += rounded_region.clear
        window.events.restored += window_api._on_restored
        window.events.restored += rounded_region.apply
        if isinstance(ui_state, dict):
            geometry_state = _WebviewGeometryState(ui_state, window)
            window.events.moved += geometry_state.moved
            window.events.resized += geometry_state.resized
            window.events.closing += geometry_state.closing
        webview.start(debug=bool(web_config.get("debug", False)))
    finally:
        reveal_stop.set()
        server.should_exit = True
        server_thread.join(timeout=10)


def run_web(config, host="127.0.0.1", port=0, open_browser=True, debug=None,
            launch_mode=None, ok_instance=None):
    """Run the browser UI, using an OS-assigned port by default."""
    uvicorn = check_web_requirements()

    from ok.ui.web.app import create_web_app

    web_config = dict(config)
    web_config["use_gui"] = False
    if debug is not None:
        web_config["debug"] = debug
    if launch_mode is None:
        gui_config = web_config.get("gui")
        launch_mode = (gui_config.get("launch_mode", "pywebview")
                       if isinstance(gui_config, dict) else None)
        if launch_mode is None:
            launch_mode = "pywebview"
    if launch_mode not in {"pywebview", "browser", "server"}:
        raise ValueError(
            "launch_mode must be 'pywebview', 'browser', or 'server'"
        )

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    browser_timer = None
    try:
        server_socket.bind((host, port))
        server_socket.listen(2048)
        selected_port = server_socket.getsockname()[1]

        web_app = create_web_app(web_config, ok_instance=ok_instance)
        webview_ready = None
        if open_browser and launch_mode == "pywebview":
            webview_ready = threading.Event()
            app_state = getattr(web_app, "state", None)
            if app_state is not None:
                app_state.webview_ready = webview_ready
        uvicorn_config = uvicorn.Config(
            web_app,
            host=host,
            port=selected_port,
            log_config=None,
        )
        _configure_server_logging()
        server = uvicorn.Server(uvicorn_config)
        url = f"http://{host}:{selected_port}"
        logger.info(f"ok script pyappify web server started:{host}:{selected_port}")
        if open_browser and launch_mode == "pywebview":
            runtime = getattr(getattr(web_app, "state", None), "runtime", None)
            ui_state = getattr(runtime, "ui_state", None)
            _run_webview(
                web_config,
                url,
                server,
                server_socket,
                ui_state=ui_state if isinstance(ui_state, dict) else None,
                ready_event=webview_ready,
            )
        else:
            if open_browser and launch_mode == "browser":
                browser_timer = threading.Timer(
                    1.0, webbrowser.open, args=(url,)
                )
                browser_timer.daemon = True
                browser_timer.start()
            server.run(sockets=[server_socket])
    except Exception as exc:
        logger.error(f"ok script pyappify web server start failed {exc}")
        raise
    finally:
        if browser_timer is not None:
            browser_timer.cancel()
        server_socket.close()

    return selected_port
