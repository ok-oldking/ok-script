from pathlib import Path

import pytest

from ok.ui.web.app import _copy_web_icon, _device_payload, _read_log


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
