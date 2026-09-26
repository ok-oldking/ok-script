from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ok import App, HeadlessApp, og
from ok.core.events import communicate


@pytest.mark.parametrize("app_type", [App, HeadlessApp])
def test_blur_initializes_overlay_without_debug_boxes(app_type, monkeypatch):
    monkeypatch.setattr(og, "executor", SimpleNamespace(basic_options={"Enable Blur": True}), raising=False)
    app = object.__new__(app_type)
    app.config = {"blur_area": lambda *_: None}
    app.ok_config = {"use_overlay": False}
    overlay = Mock()
    app.get_overlay_view = Mock(return_value=overlay)

    app.initialize_overlay()

    app.get_overlay_view.assert_called_once_with()
    overlay.set_boxes_enabled.assert_called_once_with(False)


@pytest.mark.parametrize("app_type", [App, HeadlessApp])
def test_blur_only_getter_creates_overlay_with_boxes_disabled(app_type, monkeypatch):
    monkeypatch.setattr(og, "executor", SimpleNamespace(basic_options={"Enable Blur": True}), raising=False)
    monkeypatch.setattr(og, "device_manager", SimpleNamespace(hwnd_window=None), raising=False)
    overlay = Mock()
    monkeypatch.setattr("ok.ui.overlay.Win32GdiOverlay", Mock(return_value=overlay))
    app = object.__new__(app_type)
    app.config = {"blur_area": lambda *_: None}
    app.ok_config = {"use_overlay": False}
    app.overlay_window = None
    app.exit_event = None

    try:
        assert app.get_overlay_view() is overlay
        overlay.set_boxes_enabled.assert_called_once_with(False)
    finally:
        communicate.window.disconnect(overlay.update_overlay)


@pytest.mark.parametrize("app_type", [App, HeadlessApp])
def test_blur_event_creates_overlay_after_live_setting_change(app_type, monkeypatch):
    options = {"Enable Blur": False}
    monkeypatch.setattr(og, "executor", SimpleNamespace(basic_options=options), raising=False)
    app = object.__new__(app_type)
    app.config = {"blur_area": lambda *_: None}
    app.ok_config = {"use_overlay": False}
    app.overlay_window = None
    overlay = Mock()
    app.get_overlay_view = Mock(return_value=overlay)
    patches = [object()]

    app._on_blur_patches(patches)
    app.get_overlay_view.assert_not_called()
    options["Enable Blur"] = True
    app._on_blur_patches(patches)

    app.get_overlay_view.assert_called_once_with()
    overlay.update_blur_patches.assert_called_once_with(patches)


def test_window_update_keeps_blur_only_overlay(monkeypatch):
    monkeypatch.setattr(og, "executor", SimpleNamespace(basic_options={"Enable Blur": True}), raising=False)
    app = object.__new__(App)
    app.config = {"blur_area": lambda *_: None}
    app.ok_config = {"use_overlay": False}
    overlay = Mock()
    app.overlay_window = overlay

    app.update_overlay(True, 1, 2, 100, 80, 100, 80, 1)

    overlay.update_overlay.assert_called_once_with(True, 1, 2, 100, 80, 100, 80, 1)


def test_disabling_debug_boxes_preserves_active_blur(monkeypatch):
    monkeypatch.setattr(og, "executor", SimpleNamespace(basic_options={"Enable Blur": True}), raising=False)
    app = object.__new__(HeadlessApp)
    app.config = {"blur_area": lambda *_: None}
    app.ok_config = {"use_overlay": True}
    overlay = Mock()
    app.overlay_window = overlay
    app._close_overlay = Mock()

    app.set_overlay_setting("boxes", False)

    app._close_overlay.assert_not_called()
    overlay.set_boxes_enabled.assert_called_once_with(False)


def test_disabling_last_overlay_feature_releases_window(monkeypatch):
    options = {"Enable Blur": True}
    monkeypatch.setattr(og, "executor", SimpleNamespace(basic_options=options), raising=False)
    app = object.__new__(HeadlessApp)
    app.config = {"blur_area": lambda *_: None}
    app.ok_config = {"use_overlay": False}
    app.overlay_window = Mock()
    app._close_overlay = Mock()

    options["Enable Blur"] = False
    app._on_clear_blur_patches()

    app._close_overlay.assert_called_once_with(wait=False)
