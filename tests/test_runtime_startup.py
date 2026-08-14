import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from ok import OK
from ok.core.events import communicate
from ok.device.DeviceManager import DeviceManager
from ok.util.GlobalConfig import basic_options


class FakeGlobalConfig:
    def __init__(self, auto_start=False):
        self.options = {"Auto Start Game When App Starts": auto_start}

    def get_config(self, option):
        assert option is basic_options
        return self.options


class FakeDeviceManager:
    def __init__(self):
        self.refresh_count = 0

    def refresh(self):
        self.refresh_count += 1
        return True


class FakeStartController:
    def __init__(self):
        self.calls = []

    def start(self, task=None, exit_after=False):
        self.calls.append((task, exit_after))


def make_runtime(*, auto_start=False, task=0, exit_after=False):
    runtime = object.__new__(OK)
    runtime._runtime_start_lock = threading.Lock()
    runtime._runtime_started = False
    runtime.args = {"headless": True, "task": task, "exit": exit_after}
    runtime.config = {"use_gui": False}
    runtime.global_config = FakeGlobalConfig(auto_start)
    runtime.device_manager = FakeDeviceManager()
    controller = FakeStartController()
    runtime._headless_app = SimpleNamespace(
        start_controller=controller,
        initialize_overlay=lambda: setattr(runtime, 'overlay_initialized', True),
    )
    runtime.overlay_initialized = False
    runtime._app = None
    return runtime, controller


def test_ok_checks_web_requirements_before_runtime_initialization():
    failure = SystemExit(
        "The web UI requires FastAPI and Uvicorn. Install ok-script[web]."
    )

    with patch(
        "ok.ui.web.requirements.check_web_requirements", side_effect=failure
    ) as check_requirements, patch.object(OK, "do_init") as do_init, \
            pytest.raises(SystemExit) as exit_info:
        OK({"gui": {"type": "web", "launch_mode": "server"}})

    assert exit_info.value is failure
    check_requirements.assert_called_once_with()
    do_init.assert_not_called()


def test_start_runtime_refreshes_devices_once_and_emits_start_success():
    runtime, controller = make_runtime()
    events = []
    on_start = lambda: events.append(True)
    communicate.start_success.connect(on_start)
    try:
        assert runtime.start_runtime() is True
        assert runtime.start_runtime() is False
    finally:
        communicate.start_success.disconnect(on_start)

    assert runtime.device_manager.refresh_count == 1
    assert controller.calls == []
    assert events == [True]
    assert runtime.overlay_initialized is True


def test_start_runtime_uses_core_auto_start_instead_of_ui_logic():
    runtime, controller = make_runtime(auto_start=True)

    assert runtime.start_runtime() is True

    assert runtime.device_manager.refresh_count == 0
    assert controller.calls == [(None, False)]


def test_start_runtime_applies_task_arguments_before_auto_start():
    runtime, controller = make_runtime(auto_start=True, task=3, exit_after=True)

    assert runtime.start_runtime() is True

    assert runtime.device_manager.refresh_count == 0
    assert controller.calls == [(2, True)]


def test_ok_start_routes_nested_browser_gui_to_web_server():
    runtime = object.__new__(OK)
    runtime.config = {"gui": {"type": "web", "launch_mode": "browser"}}

    with patch("ok.ui.web.server.run_web", return_value=43210) as run_web:
        assert runtime.start() == 43210

    run_web.assert_called_once_with(
        runtime.config, open_browser=True, launch_mode="browser", ok_instance=runtime
    )


def test_ok_start_routes_nested_pywebview_ui_to_pywebview():
    runtime = object.__new__(OK)
    runtime.config = {"gui": {"type": "web", "launch_mode": "pywebview"}}

    with patch("ok.ui.web.server.run_web", return_value=43210) as run_web:
        assert runtime.start() == 43210

    run_web.assert_called_once_with(
        runtime.config, open_browser=True, launch_mode="pywebview", ok_instance=runtime
    )


def test_ok_start_routes_nested_server_gui_without_opening_window():
    runtime = object.__new__(OK)
    runtime.config = {"gui": {"type": "web", "launch_mode": "server"}}

    with patch("ok.ui.web.server.run_web", return_value=43210) as run_web:
        assert runtime.start() == 43210

    run_web.assert_called_once_with(
        runtime.config, open_browser=False, launch_mode="server", ok_instance=runtime
    )


def test_ok_start_exits_when_web_requirements_are_missing():
    runtime = object.__new__(OK)
    runtime.config = {"gui": {"type": "web", "launch_mode": "server"}}
    runtime.exit_event = threading.Event()
    runtime._app = None
    runtime._headless_app = Mock()

    with patch.dict(sys.modules, {"uvicorn": None}), \
            pytest.raises(SystemExit, match="Install ok-script\\[web\\]") as exit_info:
        runtime.start()

    assert exit_info.value.code != 0
    assert runtime.exit_event.is_set()
    runtime._headless_app.quit.assert_called_once_with()


def test_device_refresh_always_publishes_completion_event():
    start_calls = []
    manager = SimpleNamespace(
        refresh_emulators=lambda current: None,
        refresh_phones=lambda current: None,
        update_pc_device=lambda: None,
        update_browser_device=lambda: None,
        exit_event=SimpleNamespace(is_set=lambda: False),
        do_start=lambda notify=True: start_calls.append(notify),
        device_dict={},
    )
    events = []
    on_devices = lambda finished: events.append(finished)
    communicate.adb_devices.connect(on_devices)
    try:
        DeviceManager.do_refresh(manager)
    finally:
        communicate.adb_devices.disconnect(on_devices)

    assert start_calls == [False]
    assert events == [True]
