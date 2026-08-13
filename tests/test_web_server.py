import logging
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from ok.ui.web.server import (
    _OkServerLogHandler, _WebviewWindowApi, _configure_server_logging,
    _enable_native_resize, _move_winforms_window, _run_webview,
    _saved_window_kwargs, _WebviewGeometryState, run_web,
)


def test_run_web_uses_available_port_and_does_not_mutate_config():
    config = {"debug": False, "use_gui": True}
    app = object()
    server = Mock()
    uvicorn_config = Mock(return_value="uvicorn-config")
    uvicorn = SimpleNamespace(Config=uvicorn_config, Server=Mock(return_value=server))

    with patch.dict(sys.modules, {"uvicorn": uvicorn}), \
            patch("ok.ui.web.server.logger") as logger, \
            patch("ok.ui.web.app.create_web_app", return_value=app) as create_app:
        selected_port = run_web(config, open_browser=False, debug=True)

    assert selected_port > 0
    assert config == {"debug": False, "use_gui": True}
    create_app.assert_called_once_with(
        {"debug": True, "use_gui": False}, ok_instance=None
    )
    uvicorn_config.assert_called_once_with(
        app, host="127.0.0.1", port=selected_port, log_config=None
    )
    server.run.assert_called_once()
    logger.info.assert_called_once_with(
        f"ok script pyappify web server started:127.0.0.1:{selected_port}"
    )
    assert server.run.call_args.kwargs["sockets"][0].fileno() == -1


def test_run_web_opens_selected_port_in_browser():
    timer = Mock()
    server = Mock()
    uvicorn = SimpleNamespace(Config=Mock(), Server=Mock(return_value=server))

    with patch.dict(sys.modules, {"uvicorn": uvicorn}), \
            patch("ok.ui.web.app.create_web_app"), \
            patch("ok.ui.web.server.threading.Timer", return_value=timer) as timer_class:
        selected_port = run_web({}, open_browser=True, launch_mode="browser")

    timer_class.assert_called_once()
    assert timer_class.call_args.args[0] == 1.0
    assert timer_class.call_args.kwargs["args"] == (
        f"http://127.0.0.1:{selected_port}",
    )
    assert timer.daemon is True
    timer.start.assert_called_once_with()
    timer.cancel.assert_called_once_with()


def test_run_web_logs_start_failure_and_reraises():
    failure = RuntimeError("startup crashed")
    server = Mock()
    server.run.side_effect = failure
    uvicorn = SimpleNamespace(Config=Mock(), Server=Mock(return_value=server))

    with patch.dict(sys.modules, {"uvicorn": uvicorn}), \
            patch("ok.ui.web.app.create_web_app"), \
            patch("ok.ui.web.server.logger") as logger, \
            pytest.raises(RuntimeError, match="startup crashed"):
        run_web({}, open_browser=False)

    logger.error.assert_called_once_with(
        "ok script pyappify web server start failed startup crashed"
    )


def test_default_web_launch_opens_pywebview():
    server = Mock()
    uvicorn = SimpleNamespace(Config=Mock(), Server=Mock(return_value=server))

    with patch.dict(sys.modules, {"uvicorn": uvicorn}), \
            patch("ok.ui.web.app.create_web_app"), \
            patch("ok.ui.web.server._run_webview") as run_webview, \
            patch("ok.ui.web.server.threading.Timer") as timer_class:
        selected_port = run_web({}, open_browser=True)

    run_webview.assert_called_once()
    assert run_webview.call_args.args[1] == f"http://127.0.0.1:{selected_port}"
    timer_class.assert_not_called()
    server.run.assert_not_called()


def test_pywebview_reuses_shared_qt_window_state():
    server = Mock()
    uvicorn = SimpleNamespace(Config=Mock(), Server=Mock(return_value=server))
    ui_state = {"window_x": 100}
    web_app = SimpleNamespace(
        state=SimpleNamespace(
            runtime=SimpleNamespace(
                ui_state=ui_state,
            ),
        ),
    )

    with patch.dict(sys.modules, {"uvicorn": uvicorn}), \
            patch("ok.ui.web.app.create_web_app", return_value=web_app), \
            patch("ok.ui.web.server._run_webview") as run_webview:
        run_web({}, open_browser=True)

    assert run_webview.call_args.kwargs["ui_state"] is ui_state


def test_pywebview_launch_mode_opens_pywebview_without_debug():
    server = Mock()
    uvicorn = SimpleNamespace(Config=Mock(), Server=Mock(return_value=server))

    with patch.dict(sys.modules, {"uvicorn": uvicorn}), \
            patch("ok.ui.web.app.create_web_app"), \
            patch("ok.ui.web.server._run_webview") as run_webview, \
            patch("ok.ui.web.server.threading.Timer") as timer_class:
        selected_port = run_web(
            {"gui": {"type": "web", "launch_mode": "pywebview"}}, open_browser=True
        )

    run_webview.assert_called_once()
    assert run_webview.call_args.args[1] == f"http://127.0.0.1:{selected_port}"
    timer_class.assert_not_called()
    server.run.assert_not_called()


def test_server_launch_mode_runs_without_opening_client():
    server = Mock()
    uvicorn = SimpleNamespace(Config=Mock(), Server=Mock(return_value=server))

    with patch.dict(sys.modules, {"uvicorn": uvicorn}), \
            patch("ok.ui.web.app.create_web_app"), \
            patch("ok.ui.web.server._run_webview") as run_webview, \
            patch("ok.ui.web.server.threading.Timer") as timer_class:
        run_web(
            {"gui": {"type": "web", "launch_mode": "server"}}, open_browser=True
        )

    run_webview.assert_not_called()
    timer_class.assert_not_called()
    server.run.assert_called_once()


def test_webview_uses_app_window_config_and_stops_server_on_close():
    window = Mock()
    shown_event = MagicMock()
    window.events = SimpleNamespace(
        shown=shown_event,
        maximized=MagicMock(),
        restored=MagicMock(),
    )
    webview = SimpleNamespace(
        create_window=Mock(return_value=window), start=Mock(), settings={}
    )
    server = Mock(should_exit=False)
    server_socket = object()
    server_thread = Mock()
    config = {
        "gui_title": "OK-WW",
        "window_size": {
            "width": 1400,
            "height": 900,
            "min_width": 1000,
            "min_height": 700,
        },
    }

    with patch.dict(sys.modules, {"webview": webview}), \
            patch("ok.ui.web.server.threading.Thread", return_value=server_thread):
        _run_webview(config, "http://127.0.0.1:12345", server, server_socket)

    webview.create_window.assert_called_once()
    create_args = webview.create_window.call_args
    assert create_args.args == ("OK-WW", "http://127.0.0.1:12345")
    assert create_args.kwargs == {
        "js_api": create_args.kwargs["js_api"],
        "width": 1400,
        "height": 900,
        "min_size": (1000, 700),
        "frameless": True,
        "resizable": True,
        "easy_drag": False,
        "shadow": True,
        "background_color": "#251e22",
    }
    assert isinstance(create_args.kwargs["js_api"], _WebviewWindowApi)
    assert create_args.kwargs["js_api"]._window is window
    assert not hasattr(create_args.kwargs["js_api"], "window")
    shown_event.__iadd__.assert_called_once_with(_enable_native_resize)
    webview.start.assert_called_once_with(debug=True)
    assert webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] is False
    server_thread.start.assert_called_once_with()
    assert server.should_exit is True
    server_thread.join.assert_called_once_with(timeout=10)


def test_webview_window_api_controls_attached_window():
    window = Mock()
    api = _WebviewWindowApi()
    api._attach(window)

    api.minimize()
    assert api.toggle_maximize() is True
    assert api.toggle_maximize() is False
    api.close()

    window.minimize.assert_called_once_with()
    window.maximize.assert_called_once_with()
    window.restore.assert_called_once_with()
    window.destroy.assert_called_once_with()


def test_enable_native_resize_restores_thickframe_style():
    native_window = SimpleNamespace(
        Handle=SimpleNamespace(ToInt32=Mock(return_value=1234)),
    )
    window = SimpleNamespace(native=native_window)

    with patch(
        "ok.ui.web.server.ctypes.windll.user32.GetWindowLongW",
        return_value=0x10000000,
    ), patch("ok.ui.web.server.ctypes.windll.user32.SetWindowLongW") as set_style, \
            patch("ok.ui.web.server.ctypes.windll.user32.SetWindowPos") as set_pos:
        assert _enable_native_resize(window) is True

    set_style.assert_called_once_with(1234, -16, 0x10040000)
    set_pos.assert_called_once_with(1234, 0, 0, 0, 0, 0, 0x0027)


def test_saved_window_kwargs_restore_qt_geometry_state():
    defaults = {"width": 1200, "height": 800}
    state = {
        "window_x": 100,
        "window_y": 200,
        "window_width": 1400,
        "window_height": 900,
        "window_maximized": True,
    }

    assert _saved_window_kwargs(defaults, state) == {
        "x": 100,
        "y": 200,
        "width": 1400,
        "height": 900,
        "maximized": True,
    }


def test_webview_geometry_state_saves_position_size_and_maximized():
    class SavedState(dict):
        def __init__(self):
            super().__init__(
                window_x=-1,
                window_y=-1,
                window_width=-1,
                window_height=-1,
                window_maximized=False,
            )
            self.save_file = Mock()

    state = SavedState()
    native_window = SimpleNamespace(WindowState="Normal")
    geometry = _WebviewGeometryState(
        state,
        SimpleNamespace(native=native_window),
    )
    timer = Mock()
    with patch("ok.ui.web.server.threading.Timer", return_value=timer):
        geometry.moved(120, 220)
        geometry.resized(1300, 850)
        native_window.WindowState = "Maximized"
        geometry.resized(1920, 1080)
    geometry.flush()

    assert state == {
        "window_x": 120,
        "window_y": 220,
        "window_width": 1300,
        "window_height": 850,
        "window_maximized": True,
    }
    state.save_file.assert_called_once_with()


def test_webview_geometry_state_ignores_stale_debounce_callback():
    state = {
        "window_x": -1,
        "window_y": -1,
        "window_width": -1,
        "window_height": -1,
        "window_maximized": False,
    }
    geometry = _WebviewGeometryState(state)
    with patch("ok.ui.web.server.threading.Timer", return_value=Mock()) as timer:
        geometry.moved(10, 20)
        first_generation = timer.call_args_list[0].kwargs["args"][0]
        geometry.resized(1200, 800)
        geometry._flush_if_current(first_generation)

    assert state["window_x"] == -1
    geometry.flush()
    assert state["window_x"] == 10
    assert state["window_width"] == 1200


def test_winforms_drag_move_uses_zero_size_with_nosize_flag():
    native_window = SimpleNamespace(
        _scale=1.5,
        Handle=SimpleNamespace(ToInt32=Mock(return_value=1234)),
    )

    with patch("ok.ui.web.server.ctypes.windll.user32.SetWindowPos") as set_window_pos:
        _move_winforms_window(native_window, 100, 200)

    set_window_pos.assert_called_once_with(
        1234, 0, 150, 300, 0, 0, 0x0001 | 0x0004 | 0x0040,
    )


def test_run_web_reuses_existing_ok_instance():
    server = Mock()
    uvicorn = SimpleNamespace(Config=Mock(), Server=Mock(return_value=server))
    ok_instance = object()

    with patch.dict(sys.modules, {"uvicorn": uvicorn}), \
            patch("ok.ui.web.app.create_web_app") as create_app:
        run_web(
            {"gui": {"type": "web"}}, open_browser=False,
            ok_instance=ok_instance,
        )

    create_app.assert_called_once_with(
        {"gui": {"type": "web"}, "use_gui": False},
        ok_instance=ok_instance,
    )


def test_server_info_logs_are_routed_to_ok_debug():
    ok_logger = Mock()
    handler = _OkServerLogHandler()
    handler.logger = ok_logger

    handler.emit(logging.LogRecord(
        "uvicorn.error", logging.INFO, __file__, 1,
        "Started server process [%d]", (123,), None,
    ))
    handler.emit(logging.LogRecord(
        "uvicorn.error", logging.WARNING, __file__, 1,
        "Server warning", (), None,
    ))

    ok_logger.debug.assert_called_once_with("Started server process [123]")
    ok_logger.warning.assert_called_once_with("Server warning")


def test_websocket_frame_debug_logs_are_not_routed_to_app_logger():
    ok_logger = Mock()
    handler = _OkServerLogHandler()
    handler.logger = ok_logger

    for message in (
        '> TEXT \'{"event":"log"}\' [198 bytes]',
        '< BINARY 01 02 03 [3 bytes]',
        '> PING ab cd [binary, 2 bytes]',
    ):
        handler.emit(logging.LogRecord(
            "uvicorn.error", logging.DEBUG, __file__, 1, message, (), None,
        ))

    ok_logger.assert_not_called()


def test_server_loggers_use_only_ok_handler():
    logger_names = ("uvicorn", "uvicorn.error", "uvicorn.access", "websockets.server")
    originals = {
        name: (list(logging.getLogger(name).handlers), logging.getLogger(name).level,
               logging.getLogger(name).propagate)
        for name in logger_names
    }
    try:
        _configure_server_logging()

        for name in logger_names:
            server_logger = logging.getLogger(name)
            assert len(server_logger.handlers) == 1
            assert isinstance(server_logger.handlers[0], _OkServerLogHandler)
            expected_level = (
                logging.INFO if name == "websockets.server" else logging.DEBUG
            )
            assert server_logger.level == expected_level
            assert server_logger.propagate is False
    finally:
        for name, (handlers, level, propagate) in originals.items():
            server_logger = logging.getLogger(name)
            server_logger.handlers = handlers
            server_logger.setLevel(level)
            server_logger.propagate = propagate
