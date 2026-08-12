from pathlib import Path
from unittest.mock import Mock

import pytest

from ok import App, HeadlessApp, _create_ok_config
from ok.ui.web.app import WebRuntime, _color_hex, _copy_web_icon, _device_payload, _read_log
from ok.util.config import Config


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
    assert loaded["show_overlay_logs"] is False


@pytest.mark.parametrize("app_type", [App, HeadlessApp])
def test_all_ui_facades_initialize_overlay_from_core_state(app_type):
    app = object.__new__(app_type)
    app.config = {}
    app.ok_config = {"use_overlay": True, "show_overlay_logs": False}
    overlay = Mock()
    app.get_overlay_view = Mock(return_value=overlay)

    app.initialize_overlay()

    app.get_overlay_view.assert_called_once_with()
    overlay.set_boxes_enabled.assert_called_once_with(True)
