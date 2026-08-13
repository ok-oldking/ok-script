import logging
import socket
import threading
import webbrowser

from ok.util.logger import Logger
from ok.core.ui_config import resolve_window_size

logger = Logger.get_logger("web_server")


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


def _run_webview(web_config, url, server, server_socket):
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError(
            "Debug web UI requires pywebview. Install ok-script[web]."
        ) from exc

    window_config = resolve_window_size(web_config)
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
    server_thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [server_socket]},
        name="web-server",
        daemon=True,
    )
    server_thread.start()
    try:
        webview.create_window(
            web_config.get("gui_title", "ok-script"),
            url,
            width=window_config.get("width", 1200),
            height=window_config.get("height", 800),
            min_size=(
                window_config.get("min_width", 800),
                window_config.get("min_height", 600),
            ),
        )
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

        uvicorn_config = uvicorn.Config(
            create_web_app(web_config, ok_instance=ok_instance),
            host=host,
            port=selected_port,
            log_config=None,
        )
        _configure_server_logging()
        server = uvicorn.Server(uvicorn_config)
        url = f"http://{host}:{selected_port}"
        logger.info(f"ok script pyappify web server started:{host}:{selected_port}")
        if open_browser and launch_mode == "pywebview":
            _run_webview(web_config, url, server, server_socket)
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
