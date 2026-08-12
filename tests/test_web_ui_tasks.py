from types import SimpleNamespace

from ok.ui.web.app import WebRuntime, _task_payload
from ok.util.config import ConfigOption


class FakeConfig(dict):
    def __init__(self, values):
        super().__init__(values)
        self.default = dict(values)

    def reset_to_default(self):
        self.clear()
        self.update(self.default)


class FakeTask:
    name = "Daily task"
    description = "Run the daily routine"
    visible = True
    group_name = None
    instructions = "Choose a window first."
    start_time = 10
    running = False
    paused = False
    enabled = False
    info = {"Result": "Ready"}
    config_description = {"Retries": "Maximum attempts"}
    config_type = {
        "Mode": {"options": ["Fast", "Safe"]},
        "Whitelist": {"options_available": ["Loot", "Heal"], "allow_duplication": True},
        "Secret": {"hidden": True},
    }
    default_config = {
        "Retries": 3, "Mode": "Safe", "Whitelist": ["Loot"],
        "Secret": "hidden", "_enabled": False,
    }

    def __init__(self):
        self.config = FakeConfig(self.default_config)
        self.executor = SimpleNamespace(
            onetime_tasks=[self],
            trigger_tasks=[],
            waiting_for_task=lambda _task: None,
        )
        self.actions = []

    def enable(self):
        self.enabled = True
        self.actions.append("enable")

    def disable(self):
        self.enabled = False
        self.actions.append("disable")

    def pause(self):
        self.paused = True
        self.actions.append("pause")

    def unpause(self):
        self.paused = False
        self.actions.append("unpause")


def runtime_for(task, is_trigger=False):
    runtime = object.__new__(WebRuntime)
    runtime.ok = SimpleNamespace(get_task=lambda _name: (task, is_trigger))
    return runtime


def test_task_payload_matches_qt_card_surface():
    task = FakeTask()

    payload = _task_payload(task)

    assert payload["instructions"] == "Choose a window first."
    assert payload["info"] == {"Result": "Ready"}
    assert [field["key"] for field in payload["config"]] == ["Retries", "Mode", "Whitelist"]
    assert payload["config"][0]["kind"] == "integer"
    assert payload["config"][1]["kind"] == "select"
    assert payload["config"][2]["kind"] == "list"
    assert payload["config"][2]["options"] == ["Loot", "Heal"]
    assert payload["config"][2]["allow_duplication"] is True


def test_onetime_actions_match_qt_task_card():
    task = FakeTask()
    runtime = runtime_for(task)

    runtime.task_action(task.name, "pause")
    runtime.task_action(task.name, "stop")

    assert task.actions == ["pause", "disable", "unpause"]


def test_trigger_actions_only_toggle_enabled_state():
    task = FakeTask()
    task.executor.onetime_tasks = []
    task.executor.trigger_tasks = [task]
    runtime = runtime_for(task, is_trigger=True)

    runtime.task_action(task.name, "enable")
    runtime.task_action(task.name, "disable")

    assert task.actions == ["enable", "disable"]


def test_task_config_can_be_updated_and_reset():
    task = FakeTask()
    runtime = runtime_for(task)

    runtime.set_task_config(task.name, "Retries", 5)
    assert task.config["Retries"] == 5

    runtime.reset_task_config(task.name)
    assert task.config["Retries"] == 3


def test_settings_match_visible_qt_global_config_cards():
    basic = FakeConfig({"Enabled": True, "Mode": "Safe"})
    option = ConfigOption(
        "Basic Options", basic.default, description="Application defaults",
        config_description={"Mode": "How to run"},
        config_type={"Mode": {"options": ["Fast", "Safe"]}},
    )
    hidden_tab_option = ConfigOption("Notification", {"Enabled": True}, show_at_tab=True)
    global_config = SimpleNamespace(
        get_all_visible_configs=lambda: [
            ("Notification", FakeConfig({"Enabled": True}), hidden_tab_option),
            ("Basic Options", basic, option),
        ],
        get_config=lambda name: basic if name == "Basic Options" else None,
    )
    runtime = object.__new__(WebRuntime)
    runtime.ok = SimpleNamespace(task_executor=SimpleNamespace(global_config=global_config))

    groups = runtime.settings()

    groups_by_name = {group["name"]: group for group in groups}
    assert set(groups_by_name) == {"Basic Options", "Notification"}
    assert groups_by_name["Basic Options"]["expanded"] is True
    assert groups_by_name["Basic Options"]["top_level"] is False
    assert groups_by_name["Basic Options"]["fields"][1]["kind"] == "select"
    assert groups_by_name["Basic Options"]["fields"][1]["description"] == "How to run"
    assert groups_by_name["Notification"]["top_level"] is True


def test_global_setting_can_be_updated_and_reset():
    config = FakeConfig({"Retries": 3})
    option = ConfigOption("Basic Options", config.default)
    global_config = SimpleNamespace(
        get_all_visible_configs=lambda: [("Basic Options", config, option)],
        get_config=lambda _name: config,
    )
    runtime = object.__new__(WebRuntime)
    runtime.ok = SimpleNamespace(task_executor=SimpleNamespace(global_config=global_config))

    updated = runtime.set_setting("Basic Options", "Retries", 5)
    assert updated["fields"][0]["value"] == 5

    reset = runtime.reset_settings("Basic Options")
    assert reset["fields"][0]["value"] == 3


def test_global_setting_subconfigs_follow_qt_visibility_rules():
    config = FakeConfig({"Advanced": False, "Details": "hidden for now"})
    option = ConfigOption(
        "Basic Options", config.default,
        config_type={"Advanced": {"sub_configs": {True: ["Details"]}}},
    )
    global_config = SimpleNamespace(
        get_all_visible_configs=lambda: [("Basic Options", config, option)],
        get_config=lambda _name: config,
    )
    runtime = object.__new__(WebRuntime)
    runtime.ok = SimpleNamespace(task_executor=SimpleNamespace(global_config=global_config))

    assert [field["key"] for field in runtime.settings()[0]["fields"]] == ["Advanced"]

    updated = runtime.set_setting("Basic Options", "Advanced", True)
    assert [field["key"] for field in updated["fields"]] == ["Advanced", "Details"]
