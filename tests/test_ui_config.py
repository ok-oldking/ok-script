import pytest

from ok.core.ui_config import DEFAULT_WINDOW_SIZE, resolve_ui_config, resolve_window_size


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


@pytest.mark.parametrize("mode", ["pywebview", "browser", "server"])
def test_nested_web_modes(mode):
    assert resolve_ui_config({"gui": {"type": "web", "launch_mode": mode}}) == {
        "type": "web", "launch_mode": mode, "window_size": DEFAULT_WINDOW_SIZE,
    }


def test_nested_web_defaults_to_pywebview():
    assert resolve_ui_config({"gui": {"type": "web"}})["launch_mode"] == "pywebview"


def test_legacy_use_gui_true_means_qt():
    size = {"width": 1300, "height": 800, "min_width": 800, "min_height": 600}

    assert resolve_ui_config({"use_gui": True, "window_size": size}) == {
        "type": "qt", "window_size": size,
    }


def test_legacy_window_size_is_fallback_for_nested_gui():
    size = {"width": 1000, "height": 700, "min_width": 800, "min_height": 600}
    config = {"gui": {"type": "web", "launch_mode": "server"}, "window_size": size}

    assert resolve_window_size(config) == size


@pytest.mark.parametrize("gui", [True, {}, {"type": "other"}, {"type": "web", "launch_mode": "other"}])
def test_invalid_nested_gui_config_is_rejected(gui):
    with pytest.raises(ValueError):
        resolve_ui_config({"gui": gui})
