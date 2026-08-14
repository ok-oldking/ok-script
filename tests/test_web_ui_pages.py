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


def test_web_client_detects_pywebview_if_ready_event_fired_before_react_effect():
    source = (Path(__file__).parents[1] / "web_src" / "src" / "App.tsx").read_text(encoding="utf-8")

    listener = 'window.addEventListener("pywebviewready", markNativeShell);'
    ready_check = 'if (window.pywebview) markNativeShell();'
    assert listener in source
    assert ready_check in source
    assert source.index(listener) < source.index(ready_check)


def test_web_client_reveals_native_window_after_initial_content_layout():
    source = (Path(__file__).parents[1] / "web_src" / "src" / "App.tsx").read_text(
        encoding="utf-8"
    )

    assert "Promise.allSettled([load(), loadSettings(), loadNavigation()])" in source
    assert "if (!initialContentLoaded) return;" in source
    assert "runtimeApi.contentReady()" in source
    assert source.count("window.requestAnimationFrame(") >= 3
    assert 'classList.remove("pywebview-starting")' in source

    styles = (Path(__file__).parents[1] / "web_src" / "src" / "styles.css").read_text(
        encoding="utf-8"
    )
    assert ".pywebview-starting .switch-track" in styles
    assert ".pywebview-starting .switch-thumb { transition: none; }" in styles


def test_web_client_has_winui_window_frame_and_navigation_motion():
    root = Path(__file__).parents[1]
    source = (root / "web_src" / "src" / "App.tsx").read_text(encoding="utf-8")
    styles = (root / "web_src" / "src" / "styles.css").read_text(encoding="utf-8")

    assert 'className={`nav-selection-indicator ${navIndicatorVisible ? "visible" : ""}`}' in source
    assert "key={activePage}" in source
    assert "border-radius: var(--window-radius)" in styles
    assert "grid-template-rows: 32px minmax(0, 1fr); border: 0" in styles
    assert "cubic-bezier(.1, .9, .2, 1)" in styles
    assert "@keyframes winui-page-enter" in styles
    assert "@media (prefers-reduced-motion: reduce)" in styles
    assert "window-resize-handle" not in source


def test_web_tabs_share_the_same_outer_page_padding():
    styles = (Path(__file__).parents[1] / "web_src" / "src" / "styles.css").read_text(
        encoding="utf-8"
    )

    assert "padding: var(--page-padding-block) var(--page-padding-inline)" in styles
    assert "--page-padding-block: 16px" in styles
    assert "--page-padding-inline: 16px" in styles
    assert "--page-padding-block: 18px" not in styles
    assert ".task-content { display: block; overflow: auto; scrollbar-width" in styles
    assert ".settings-page { width: 100%; margin: 0; padding: 0; }" in styles
    assert ".workspace-page { width: 100%; margin: 0; padding: 0; }" in styles
    assert ".task-list { display: grid; gap: 8px; padding: 0; }" in styles


def test_web_tab_surface_has_only_a_top_left_radius_and_identity_cards_are_compact():
    styles = (Path(__file__).parents[1] / "web_src" / "src" / "styles.css").read_text(
        encoding="utf-8"
    )

    assert (
        "padding: var(--page-padding-block) var(--page-padding-inline);\n"
        "  border: 0; border-radius: 12px 0 0 0;"
    ) in styles
    assert "background: var(--chrome-bg); border-right: 0;" in styles
    assert ".start-card.about-identity { min-height: 68px; padding: 10px 14px; }" in styles
    assert ".about-identity .app-avatar { width: 40px; height: 40px; }" in styles
    assert ".about-identity h1 { margin: 0; font-size: 1rem; }" in styles


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
