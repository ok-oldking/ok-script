import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ok import App, HeadlessApp, _create_ok_config
from ok.ui.web.app import (
    WebRuntime, _color_hex, _copy_web_icon, _device_payload, _read_log, create_web_app,
    _EventSessionRegistry, _send_websocket_payload,
    _wait_for_websocket_disconnect,
)
from ok.util.config import Config


def test_create_web_app_exits_when_fastapi_is_missing():
    with patch.dict(sys.modules, {"fastapi": None}), \
            pytest.raises(SystemExit, match="Install ok-script\\[web\\]") as exit_info:
        create_web_app({})

    assert exit_info.value.code != 0


def test_copy_web_icon_prepares_static_asset(tmp_path: Path):
    source = tmp_path / "source" / "app.png"
    source.parent.mkdir()
    source.write_bytes(b"png-data")
    static = tmp_path / "static"

    url = _copy_web_icon({"gui_icon": str(source)}, static)

    assert url.startswith("/static/app-icon.png?version=")
    assert (static / "app-icon.png").read_bytes() == b"png-data"


def test_copy_web_icon_ignores_qt_resource_path(tmp_path: Path):
    assert _copy_web_icon({"gui_icon": ":/icon/icon.ico"}, tmp_path) is None


def test_device_payload_includes_filterable_window_metadata():
    payload = _device_payload({
        "imei": "pc_1",
        "device": "windows",
        "nick": "Game Window",
        "exe": "game.exe",
        "full_path": r"C:\Games\game.exe",
        "address": "",
        "resolution": "1920x1080",
        "connected": True,
    }, "pc_1")

    assert payload["selected"] is True
    assert payload["label"] == "PC Connected: Game Window 1920x1080"
    assert "game.exe" in payload["keywords"]


def test_theme_ui_exposes_system_accent_palette(monkeypatch):
    palette = {"light": "#0067c0", "dark": "#4cc2ff"}
    monkeypatch.setattr("ok.ui.web.app._windows_system_accents", lambda: palette)

    assert _color_hex(0, 103, 192) == "#0067c0"
    assert object.__new__(WebRuntime).theme_ui() == {"system_accent": palette}


def test_web_runtime_issues_url_safe_event_session_key(monkeypatch):
    monkeypatch.setattr("ok.OK", Mock(return_value=Mock()))

    runtime = WebRuntime({})

    assert len(runtime.event_session_key) >= 16
    assert runtime.event_session_key.replace("-", "").replace("_", "").isalnum()


def test_web_status_reports_starting_before_executor_runs():
    runtime = object.__new__(WebRuntime)
    runtime.ok = SimpleNamespace(
        task_executor=SimpleNamespace(
            current_task=None,
            basic_options={"Start/Stop": "None"},
            paused=True,
            thread=None,
            get_all_tasks=lambda: [],
        ),
        headless_app=SimpleNamespace(
            start_controller=SimpleNamespace(starting=True)
        ),
    )

    assert runtime.status()["starting"] is True


def test_read_log_filters_complete_records(tmp_path: Path):
    log = tmp_path / "ok-script.log"
    log.write_text(
        "2026-08-11 10:00:00,000 INFO startup\n"
        "continued info\n"
        "2026-08-11 10:00:01,000 ERROR capture failed\n"
        "trace detail\n",
        encoding="utf-8",
    )

    result = _read_log(log, level="ERROR")

    assert result["line_count"] == 2
    assert "capture failed" in result["text"]
    assert "trace detail" in result["text"]
    assert "startup" not in result["text"]


def test_read_log_validates_level(tmp_path: Path):
    with pytest.raises(ValueError, match="Unknown log level"):
        _read_log(tmp_path / "missing.log", level="verbose")


def test_core_ui_config_loads_persisted_overlay_state(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Config, "config_folder", str(tmp_path))
    (tmp_path / "_ok.json").write_text(
        '{"window_x": -1, "window_y": -1, "window_width": -1, "window_height": -1, '
        '"window_maximized": false, "navigation_expanded": true, '
        '"use_overlay": true, "show_overlay_logs": false}',
        encoding="utf-8",
    )

    loaded = _create_ok_config({})

    assert loaded["use_overlay"] is True
    assert "show_overlay_logs" not in loaded


@pytest.mark.parametrize("app_type", [App, HeadlessApp])
def test_all_ui_facades_initialize_overlay_from_core_state(app_type):
    app = object.__new__(app_type)
    app.config = {}
    app.ok_config = {"use_overlay": True}
    overlay = Mock()
    app.get_overlay_view = Mock(return_value=overlay)

    app.initialize_overlay()

    app.get_overlay_view.assert_called_once_with()
    overlay.set_boxes_enabled.assert_called_once_with(True)


@pytest.mark.parametrize("app_type", [App, HeadlessApp])
def test_disabled_overlay_is_not_initialized(app_type):
    app = object.__new__(app_type)
    app.config = {"blur_area": lambda *_: None}
    app.ok_config = {"use_overlay": False}
    app.get_overlay_view = Mock()

    app.initialize_overlay()

    app.get_overlay_view.assert_not_called()


@pytest.mark.parametrize("app_type", [App, HeadlessApp])
def test_disabled_overlay_getter_does_not_create_native_window(app_type):
    app = object.__new__(app_type)
    app.ok_config = {"use_overlay": False}
    app.overlay_window = None

    assert app.get_overlay_view() is None
    assert app.overlay_window is None


def test_web_overlay_toggle_resyncs_latest_capture_window():
    app = object.__new__(HeadlessApp)
    app.config = {}
    app.ok_config = {"use_overlay": False}
    app.overlay_window = Mock()
    app.get_overlay_view = Mock(return_value=app.overlay_window)

    from ok import og
    previous_device_manager = getattr(og, "device_manager", None)
    source_window = object()
    og.device_manager = SimpleNamespace(hwnd_window=source_window)
    try:
        app.set_overlay_setting("boxes", True)
    finally:
        og.device_manager = previous_device_manager

    app.overlay_window.sync_source_window.assert_called_once_with(source_window)
    app.overlay_window.set_boxes_enabled.assert_called_once_with(True)


def test_turning_boxes_off_closes_and_releases_overlay():
    app = object.__new__(HeadlessApp)
    app.config = {"blur_area": lambda *_: None}
    app.ok_config = {"use_overlay": True}
    overlay = Mock()
    app.overlay_window = overlay

    app.set_overlay_setting("boxes", False)

    overlay.close.assert_called_once_with()
    assert app.overlay_window is None


def test_capture_updates_cannot_resurrect_disabled_overlay():
    app = object.__new__(App)
    app.ok_config = {"use_overlay": False}
    app.overlay_window = Mock()
    app._close_overlay = Mock()
    app.get_overlay_view = Mock()

    app.update_overlay(True, 1, 2, 100, 80, 100, 80, 1)

    app._close_overlay.assert_called_once_with(wait=False)
    app.get_overlay_view.assert_not_called()


def test_removed_overlay_log_setting_is_rejected():
    app = object.__new__(HeadlessApp)
    app.config = {}
    app.ok_config = {"use_overlay": False}
    app.overlay_window = None

    with pytest.raises(ValueError, match="Unknown overlay setting"):
        app.set_overlay_setting("logs", True)


def test_headless_notification_formats_and_submits_to_manager():
    app = object.__new__(HeadlessApp)
    app.notification_manager = Mock()
    app.tr = lambda value: f"translated:{value}"
    images = [object()]

    app.show_notification("Failed {count}", "Task", True, True, None,
                          {"count": 2}, images)

    app.notification_manager.submit.assert_called_once_with(
        "translated:Task", "translated:Failed 2", images)
    app.notification_manager.notify_system.assert_called_once_with(
        "translated:Task", "translated:Failed 2", True, True)


def test_headless_notification_respects_system_notification_setting():
    app = object.__new__(HeadlessApp)
    app.notification_manager = Mock()
    app.tr = lambda value: value

    app.show_notification("Done", "Task", False, True)

    app.notification_manager.notify_system.assert_called_once_with(
        "Task", "Done", False, True)


def test_websocket_post_close_send_ends_event_stream_cleanly():
    websocket = SimpleNamespace(send_json=AsyncMock(side_effect=RuntimeError(
        "Unexpected ASGI message 'websocket.send', after sending 'websocket.close'."
    )))

    sent = asyncio.run(_send_websocket_payload(websocket, {"event": "notification"}))

    assert sent is False


def test_websocket_send_does_not_hide_unrelated_runtime_errors():
    websocket = SimpleNamespace(send_json=AsyncMock(side_effect=RuntimeError("serialization failed")))

    with pytest.raises(RuntimeError, match="serialization failed"):
        asyncio.run(_send_websocket_payload(websocket, {"event": "notification"}))


def test_websocket_disconnect_listener_consumes_idle_disconnect():
    websocket = SimpleNamespace(receive=AsyncMock(side_effect=[
        {"type": "websocket.receive", "text": "ignored"},
        {"type": "websocket.disconnect", "code": 1001},
    ]))

    asyncio.run(_wait_for_websocket_disconnect(websocket))

    assert websocket.receive.await_count == 2


def test_new_event_session_supersedes_old_connection_safely():
    registry = _EventSessionRegistry()
    old_wake = Mock()
    new_wake = Mock()

    old_token = registry.register("browser-session-key", old_wake)
    new_token = registry.register("browser-session-key", new_wake)

    old_wake.assert_called_once_with()
    new_wake.assert_not_called()
    assert registry.is_active("browser-session-key", old_token) is False
    assert registry.is_active("browser-session-key", new_token) is True

    registry.unregister("browser-session-key", old_token)
    assert registry.is_active("browser-session-key", new_token) is True

    registry.unregister("browser-session-key", new_token)
    assert registry.is_active("browser-session-key", new_token) is False
