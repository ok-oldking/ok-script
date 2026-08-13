import ctypes
import logging
import os
import socket
import threading
import webbrowser

from ok.util.logger import Logger
from ok.core.ui_config import resolve_window_size

logger = Logger.get_logger("web_server")

_GWL_STYLE = -16
_WS_THICKFRAME = 0x00040000
_SWP_REFRESH_FRAME = 0x0001 | 0x0002 | 0x0004 | 0x0020


def _enable_native_resize(window):
    """Restore the Win32 sizing style removed by a frameless WinForms form."""
    if os.name != "nt":
        return False
    native_window = getattr(window, "native", None)
    if native_window is None:
        return False

    hwnd = native_window.Handle.ToInt32()
    style = ctypes.windll.user32.GetWindowLongW(hwnd, _GWL_STYLE)
    if not style & _WS_THICKFRAME:
        ctypes.windll.user32.SetWindowLongW(
            hwnd,
            _GWL_STYLE,
            style | _WS_THICKFRAME,
        )
        ctypes.windll.user32.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            _SWP_REFRESH_FRAME,
        )
    return True


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


class _WebviewWindowApi:
    """Window controls exposed only to the bundled pywebview client."""

    def __init__(self):
        # pywebview recursively serializes public js_api attributes. Keep the
        # native Window private or it will walk the WinForms/.NET object graph.
        self._window = None
        self.maximized = False

    def _attach(self, window, maximized=False):
        self._window = window
        self.maximized = maximized

    def _on_maximized(self):
        self.maximized = True

    def _on_restored(self):
        self.maximized = False

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


def _run_webview(web_config, url, server, server_socket, ui_state=None):
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
    try:
        saved_window = _saved_window_kwargs(window_config, ui_state)
        window_api = _WebviewWindowApi()
        window = webview.create_window(
            web_config.get("gui_title", "ok-script"),
            url,
            js_api=window_api,
            min_size=(
                window_config.get("min_width", 800),
                window_config.get("min_height", 600),
            ),
            frameless=True,
            resizable=True,
            easy_drag=False,
            shadow=True,
            background_color="#251e22",
            **saved_window,
        )
        window_api._attach(window, saved_window.get("maximized", False))
        window.events.maximized += window_api._on_maximized
        window.events.restored += window_api._on_restored
        if os.name == "nt":
            window.events.shown += _enable_native_resize
        if isinstance(ui_state, dict):
            geometry_state = _WebviewGeometryState(ui_state, window)
            window.events.moved += geometry_state.moved
            window.events.resized += geometry_state.resized
            window.events.closing += geometry_state.closing
        webview.start(debug=True)
    finally:
        server.should_exit = True
        server_thread.join(timeout=10)


def run_web(config, host="127.0.0.1", port=0, open_browser=True, debug=None,
            launch_mode=None, ok_instance=None):
    """Run the browser UI, using an OS-assigned port by default."""
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError(
            "The web UI requires FastAPI and Uvicorn. Install ok-script[web]."
        ) from exc

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
