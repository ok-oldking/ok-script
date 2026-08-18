from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from ok.task.web import (
    WebTabConfig,
    WebCustomTab,
    call_task_tab_operation,
    configured_web_custom_tabs,
    task_tab_action,
    task_tab_query,
)
from ok.ui.web.app import WebRuntime, create_web_app, register_task_tabs


class ExampleTask:
    name = "Example Task"

    def __init__(self, asset_dir):
        self.web_tab = WebTabConfig(
            id="example",
            name="Example",
            asset_dir=asset_dir,
            task_controls=False,
        )
        self.saved = None

    @task_tab_query("state")
    def state(self):
        return {"ready": True}

    @task_tab_action("save")
    def save(self, payload):
        self.saved = payload["value"]
        return {"saved": self.saved}

    def private_method(self):
        raise AssertionError("must not be remotely callable")


def make_asset_dir(tmp_path: Path):
    folder = tmp_path / "web"
    folder.mkdir()
    (folder / "index.js").write_text("export function mount() {}", encoding="utf-8")
    return folder


def test_task_tab_registration_and_allowlisted_dispatch(tmp_path):
    task = ExampleTask(make_asset_dir(tmp_path))
    tabs = register_task_tabs([task])

    assert tabs[0].manifest() == {
        "id": "example",
        "name": "Example",
        "icon": "code",
        "position": "scroll",
        "add_after_default_tabs": True,
        "task_controls": False,
        "task_name": "Example Task",
        "task_class_name": "ExampleTask",
        "module_url": "/task-tabs/example/assets/index.js",
    }
    assert call_task_tab_operation(task, "query", "state") == {"ready": True}
    assert call_task_tab_operation(task, "action", "save", {"value": 3}) == {"saved": 3}
    with pytest.raises(ValueError, match="Unknown task tab action"):
        call_task_tab_operation(task, "action", "private_method", {})


def test_task_tab_registration_rejects_duplicate_ids(tmp_path):
    asset_dir = make_asset_dir(tmp_path)
    with pytest.raises(ValueError, match="Duplicate task tab id"):
        register_task_tabs([ExampleTask(asset_dir), ExampleTask(asset_dir)])


def test_registration_does_not_evaluate_unrelated_task_properties(tmp_path):
    class TaskWithBlockingProperties(ExampleTask):
        @property
        def frame(self):
            raise AssertionError("unrelated properties must not run during discovery")

    task = TaskWithBlockingProperties(make_asset_dir(tmp_path))

    assert register_task_tabs([task])[0].manifest()["id"] == "example"
    assert call_task_tab_operation(task, "query", "state") == {"ready": True}


def test_legacy_qt_custom_tabs_are_ignored_by_web_discovery(tmp_path):
    runtime = object.__new__(WebRuntime)
    runtime.ok = SimpleNamespace(
        config={"custom_tabs": [["missing.qt.module", "LegacyQtTab"]]},
        task_manager=None,
        task_executor=SimpleNamespace(
            get_all_tasks=lambda: [], onetime_tasks=[], trigger_tasks=[]
        ),
    )
    runtime._task_tabs = register_task_tabs(runtime.executor.get_all_tasks())

    assert runtime.task_tabs() == []
    assert runtime.navigation()["task_tabs"] == []


def test_web_page_tasks_use_separate_explicit_config(monkeypatch):
    class ConfiguredPage(WebCustomTab):
        pass

    module = SimpleNamespace(ConfiguredPage=ConfiguredPage)
    monkeypatch.setattr("ok.task.web.importlib.util.find_spec", lambda _name: object())
    monkeypatch.setattr("ok.task.web.importlib.import_module", lambda _name: module)

    assert configured_web_custom_tabs([
        ["example.web_page", "ConfiguredPage"]
    ]) == [["example.web_page", "ConfiguredPage"]]


def test_task_tab_http_dispatch_and_assets(tmp_path):
    try:
        from fastapi.testclient import TestClient
    except (ImportError, RuntimeError) as error:
        pytest.skip(f"FastAPI TestClient is unavailable: {error}")
    task = ExampleTask(make_asset_dir(tmp_path))
    registrations = register_task_tabs([task])
    runtime = Mock()
    runtime.executor.get_all_tasks.return_value = [task]
    runtime._task_tabs = registrations
    runtime.task_tabs.side_effect = lambda: [item.manifest() for item in registrations]
    runtime.task_tab_call.side_effect = lambda tab_id, kind, operation, payload: (
        call_task_tab_operation(task, kind, operation, payload)
    )

    with patch("ok.ui.web.app.WebRuntime", return_value=runtime):
        app = create_web_app({"gui_title": "Test"})

    with TestClient(app) as client:
        assert client.get("/api/task-tabs").json()[0]["id"] == "example"
        assert client.post(
            "/api/task-tabs/example/query/state", json={}
        ).json() == {"ready": True}
        assert client.post(
            "/api/task-tabs/example/action/save", json={"value": 7}
        ).json() == {"saved": 7}
        assert client.get("/task-tabs/example/assets/index.js").status_code == 200
