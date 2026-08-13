import logging
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from ok.ui.web.server import (
    _OkServerLogHandler, _configure_server_logging, _run_webview, run_web,
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
    webview = SimpleNamespace(create_window=Mock(), start=Mock(), settings={})
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

    webview.create_window.assert_called_once_with(
        "OK-WW", "http://127.0.0.1:12345", width=1400, height=900,
        min_size=(1000, 700),
    )
    webview.start.assert_called_once_with(debug=True)
    assert webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] is False
    server_thread.start.assert_called_once_with()
    assert server.should_exit is True
    server_thread.join.assert_called_once_with(timeout=10)


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
