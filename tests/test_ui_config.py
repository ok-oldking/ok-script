from pathlib import Path

import pytest

from ok.core.ui_config import DEFAULT_WINDOW_SIZE, resolve_gui_icon, resolve_ui_config, resolve_window_size


@pytest.mark.parametrize("config", [{}, {"gui_icon": None}, {"gui_icon": ""}])
def test_default_icon_is_a_bundled_png_independent_of_working_directory(config, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    icon = Path(resolve_gui_icon(config))

    assert icon.is_absolute()
    assert icon.is_relative_to(Path(__file__).resolve().parents[1] / "ok")
    assert icon.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize("icon", ["assets/custom.png", "C:/app/custom.png", ":/icon/custom.png"])
def test_explicit_icon_is_preserved(icon):
    assert resolve_gui_icon({"gui_icon": icon}) == icon


def test_missing_gui_config_is_headless():
    assert resolve_ui_config({}) is None
    assert resolve_ui_config({"use_gui": False}) is None


def test_nested_qt_config_uses_nested_window_size():
    size = {"width": 1400, "height": 900, "min_width": 900, "min_height": 600}

    assert resolve_ui_config({
        "gui": {"type": "qt", "window_size": size},
        "use_gui": False,
        "window_size": {"width": 1},
    }) == {"type": "qt", "window_size": size}


def test_nested_qt_defaults_window_size():
    assert resolve_ui_config({"gui": {"type": "qt"}}) == {
        "type": "qt", "window_size": DEFAULT_WINDOW_SIZE,
    }


def test_legacy_use_gui_true_means_qt():
    size = {"width": 1300, "height": 800, "min_width": 800, "min_height": 600}

    assert resolve_ui_config({"use_gui": True, "window_size": size}) == {
        "type": "qt", "window_size": size,
    }


def test_legacy_window_size_is_fallback_for_nested_gui():
    size = {"width": 1000, "height": 700, "min_width": 800, "min_height": 600}
    config = {"gui": {"type": "qt"}, "window_size": size}

    assert resolve_window_size(config) == size


@pytest.mark.parametrize("gui", [True, {}, {"type": "other"}, {"type": "web"}])
def test_invalid_nested_gui_config_is_rejected(gui):
    with pytest.raises(ValueError):
        resolve_ui_config({"gui": gui})
