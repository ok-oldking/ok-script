import json
from pathlib import Path
from types import SimpleNamespace

from ok.ui.web.app import WebRuntime


class FakeTaskManager:
    def __init__(self, folder):
        self.task_folder = str(folder)
        self.has_custom = True
        self.task_map = {}
        self.task_errors = {}
        self.loaded = []

    def load_single_user_task(self, path):
        self.loaded.append(path)

    def reload_task_code(self, _task):
        pass

    def delete_task(self, _task):
        raise AssertionError("Unexpected mapped task")


def make_runtime(tmp_path):
    runtime = object.__new__(WebRuntime)
    manager = FakeTaskManager(tmp_path / "ok_tasks")
    runtime.ok = SimpleNamespace(
        config={"gui_title": "Test App", "version": "1.2.3", "debug": False, "links": {"github": "https://example.test"}},
        task_manager=manager,
        task_executor=SimpleNamespace(get_all_tasks=lambda: [], onetime_tasks=[], trigger_tasks=[]),
    )
    runtime.icon_url = "/static/app-icon.png"
    runtime._schedule_manager = None
    return runtime


def test_about_and_navigation_are_runtime_driven(tmp_path):
    runtime = make_runtime(tmp_path)

    assert runtime.navigation() == {
        "triggers": False, "tasks": False, "script": True,
        "templates": True, "schedule": False,
    }
    assert runtime.about()["title"] == "Test App"
    assert runtime.about()["links"]["github"] == "https://example.test"
    assert runtime.about()["projects"][0]["website"] == "https://ok-script.com/"


def test_about_omits_the_current_project_from_other_projects(tmp_path):
    runtime = make_runtime(tmp_path)
    runtime.ok.config["links"]["github"] = {"en_US": "https://github.com/ok-oldking/ok-wuthering-waves/"}

    project_urls = [project["url"] for project in runtime.about()["projects"]]

    assert "https://github.com/ok-oldking/ok-wuthering-waves" not in project_urls


def test_about_supports_qt_locale_first_links_config(tmp_path):
    runtime = make_runtime(tmp_path)
    runtime.ok.config["links"] = {
        "default": {
            "github": "https://github.com/ok-oldking/ok-wuthering-waves",
            "discord": "https://discord.gg/example",
        },
        "zh_CN": {"github": "https://github.com/ok-oldking/ok-wuthering-waves"},
    }

    about = runtime.about()

    assert about["links"]["default"]["discord"] == "https://discord.gg/example"
    assert "https://github.com/ok-oldking/ok-wuthering-waves" not in [project["url"] for project in about["projects"]]


def test_web_client_routes_tray_events_to_browser_notifications():
    source = (Path(__file__).parents[1] / "web_src" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert 'event.args[3] === true && systemNotificationsEnabled' in source
    assert 'new Notification(title, { body: message, icon: iconUrl || undefined })' in source
    assert 'Notification.requestPermission()' in source


def test_script_crud_stays_inside_custom_task_folder(tmp_path):
    runtime = make_runtime(tmp_path)

    created = runtime.create_script("HelloTask", "Hello", "Example")
    assert created["name"] == "HelloTask.py"
    assert "class HelloTask" in created["code"]

    saved = runtime.save_script("HelloTask.py", created["code"].replace("pass", "return"))
    assert "return" in saved["code"]
    assert [item["name"] for item in runtime.scripts()] == ["HelloTask.py"]

    runtime.delete_script("HelloTask.py")
    assert runtime.scripts() == []


def test_template_gallery_reads_categories_and_cleans_coco(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runtime = make_runtime(tmp_path)
    folder = tmp_path / "ok_templates"
    folder.mkdir()
    (folder / "sample.png").write_bytes(b"image")
    (folder / "coco_annotations.json").write_text(json.dumps({
        "images": [{"id": 1, "file_name": "sample.png"}],
        "categories": [{"id": 2, "name": "button"}],
        "annotations": [{"id": 3, "image_id": 1, "category_id": 2}],
    }), encoding="utf-8")

    assert runtime.templates()[0]["categories"] == ["button"]
    runtime.delete_template("sample.png")
    coco = json.loads((folder / "coco_annotations.json").read_text(encoding="utf-8"))
    assert coco["images"] == []
    assert coco["annotations"] == []


def test_script_paths_reject_traversal(tmp_path):
    runtime = make_runtime(tmp_path)
    try:
        runtime.read_script("../outside.py")
    except ValueError as exc:
        assert "Invalid script name" in str(exc)
    else:
        raise AssertionError("Traversal should be rejected")
