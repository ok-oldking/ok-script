"""
计划任务索引启动校正补丁的单元测试（完全隔离）。

不依赖 ok 全局（monkeypatch `_onetime_tasks` 返回假任务列表），
不调用真实 Windows COM（monkeypatch `_register_task_xml`），
缓存文件使用 tmp_path（monkeypatch `_cache_file`）。
"""

import json
import sys

import pytest

import ok.ui.qt.tasks.schedule_index_sync as sync_patch


class _FakeTask:
    """带 name 属性的假任务。"""

    def __init__(self, name):
        self.name = name


def _make_cache_entry(path, name, actions="", xml_config="", task_index=-1):
    return {
        "path": path,
        "name": name,
        "actions": actions,
        "xml_config": xml_config,
        "task_index": task_index,
        "enabled": True,
        "status": "Ready",
        "trigger_type": "Daily",
    }


def _xml_with(args_text):
    return (
        '<?xml version="1.0" encoding="UTF-16"?><Task version="1.2">'
        f"<Actions Context=\"Author\"><Exec><Arguments>{args_text}</Arguments></Exec></Actions>"
        "</Task>"
    )


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """完全隔离的测试环境。"""
    sync_patch.reset_sync_guard()
    cache_file = tmp_path / "schedule_tasks_cache.json"
    monkeypatch.setattr(sync_patch, "_cache_file", lambda: cache_file)
    monkeypatch.setattr(sync_patch, "_schedule_root_path", lambda: "\\ok-ef")
    registered = []
    monkeypatch.setattr(
        sync_patch, "_register_task_xml", lambda path, xml: registered.append((path, xml))
    )
    yield sync_patch, cache_file, registered
    sync_patch.reset_sync_guard()


def test_replace_task_target():
    """改写 -t 目标：数字、XML 结尾、任务名、空串。"""
    assert sync_patch._replace_task_target("main.py -t 15 -e", 3) == "main.py -t 3 -e"
    assert (
        sync_patch._replace_task_target("<Arguments>main.py -t 15</Arguments>", 3)
        == "<Arguments>main.py -t 3</Arguments>"
    )
    assert (
        sync_patch._replace_task_target("<Arguments>main.py -t 日常任务 -e</Arguments>", 3)
        == "<Arguments>main.py -t 3 -e</Arguments>"
    )
    assert sync_patch._replace_task_target("", 3) == ""


def test_extract_task_target():
    """从 actions / xml_config 提取当前 -t 目标（索引或历史任务名）。"""
    item = _make_cache_entry("\\ok-ef\\x", "日常任务", actions="main.py -t 15 -e", task_index=15)
    assert sync_patch._extract_task_target(item) == "15"

    item2 = _make_cache_entry(
        "\\ok-ef\\x", "日常任务", xml_config=_xml_with("main.py -t 日常任务")
    )
    assert sync_patch._extract_task_target(item2) == "日常任务"

    item3 = _make_cache_entry("\\ok-ef\\x", "日常任务")
    assert sync_patch._extract_task_target(item3) is None


def test_rewrites_stale_index(isolated):
    """旧索引（-t 15）应按 name 改写为当前新索引（-t 1）。"""
    patch_mod, cache_file, registered = isolated
    onetime_tasks = [_FakeTask("日常任务"), _FakeTask("自动送货"), _FakeTask("影拓丰碑")]
    data = {
        "\\ok-ef\\daily_abc": _make_cache_entry(
            "\\ok-ef\\daily_abc",
            "日常任务",
            actions="python.exe main.py -t 15 -e",
            xml_config=_xml_with("main.py -t 15 -e"),
            task_index=15,
        )
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 1

    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    entry = saved["\\ok-ef\\daily_abc"]
    assert entry["task_index"] == 1
    assert "-t 1" in entry["actions"]
    assert "-t 1" in entry["xml_config"]
    assert "-t 15" not in entry["actions"]
    assert "-t 15" not in entry["xml_config"]
    # Windows 计划任务用新 XML 同步注册
    assert registered == [("\\ok-ef\\daily_abc", entry["xml_config"])]


def test_rewrites_historical_name_target(isolated):
    """历史迁移成的任务名 -t 也应改写回数字索引。"""
    patch_mod, cache_file, registered = isolated
    onetime_tasks = [_FakeTask("日常任务"), _FakeTask("自动送货")]
    data = {
        "\\ok-ef\\daily_abc": _make_cache_entry(
            "\\ok-ef\\daily_abc",
            "日常任务",
            actions="main.py -t 日常任务 -e",
            xml_config=_xml_with("main.py -t 日常任务 -e"),
            task_index=-1,
        )
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 1

    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    entry = saved["\\ok-ef\\daily_abc"]
    assert entry["task_index"] == 1
    assert "-t 1" in entry["actions"]
    assert "日常任务" not in entry["actions"].split("-t ")[-1].split(" ")[0]
    assert registered


def test_multiple_tasks_corrected(isolated):
    """多个任务各自按 name 校正到新索引。"""
    patch_mod, cache_file, registered = isolated
    onetime_tasks = [
        _FakeTask("日常任务"),
        _FakeTask("x2"),
        _FakeTask("x3"),
        _FakeTask("自动送货"),
        _FakeTask("x5"),
        _FakeTask("x6"),
        _FakeTask("影拓丰碑"),
        _FakeTask("启动一次游戏"),
    ]
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "\\ok-ef\\daily", "日常任务", actions="main.py -t 15 -e",
            xml_config=_xml_with("main.py -t 15 -e"), task_index=15),
        "\\ok-ef\\deliver": _make_cache_entry(
            "\\ok-ef\\deliver", "自动送货", actions="main.py -t 16 -e",
            xml_config=_xml_with("main.py -t 16 -e"), task_index=16),
        "\\ok-ef\\monument": _make_cache_entry(
            "\\ok-ef\\monument", "影拓丰碑", actions="main.py -t 17 -e",
            xml_config=_xml_with("main.py -t 17 -e"), task_index=17),
        "\\ok-ef\\once": _make_cache_entry(
            "\\ok-ef\\once", "启动一次游戏", actions="main.py -t 18 -e",
            xml_config=_xml_with("main.py -t 18 -e"), task_index=18),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 4

    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    expected = {
        "\\ok-ef\\daily": 1,
        "\\ok-ef\\deliver": 4,
        "\\ok-ef\\monument": 7,
        "\\ok-ef\\once": 8,
    }
    for path, index in expected.items():
        assert saved[path]["task_index"] == index
        assert f"-t {index}" in saved[path]["actions"]
    assert len(registered) == 4


def test_skips_other_app_read_only_tasks(isolated):
    """其它 ok-* 应用的任务（只读）不应被改写。"""
    patch_mod, cache_file, registered = isolated
    onetime_tasks = [_FakeTask("日常任务")]
    data = {
        "\\ok-other\\task1": _make_cache_entry(
            "\\ok-other\\task1", "日常任务", actions="main.py -t 15 -e",
            xml_config=_xml_with("main.py -t 15 -e"), task_index=15),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 0
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert saved["\\ok-other\\task1"]["task_index"] == 15
    assert "-t 15" in saved["\\ok-other\\task1"]["actions"]
    assert registered == []


def test_skips_unknown_task_name(isolated):
    """name 在当前 onetime_tasks 中不存在时跳过，不写缓存不调 COM。"""
    patch_mod, cache_file, registered = isolated
    onetime_tasks = [_FakeTask("日常任务")]
    data = {
        "\\ok-ef\\stale": _make_cache_entry(
            "\\ok-ef\\stale", "已删除的任务", actions="main.py -t 15 -e",
            xml_config=_xml_with("main.py -t 15 -e"), task_index=15),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 0
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert saved["\\ok-ef\\stale"]["task_index"] == 15
    assert registered == []


def test_idempotent_already_correct(isolated):
    """已经是正确索引时不写缓存、不调 COM。"""
    patch_mod, cache_file, registered = isolated
    onetime_tasks = [_FakeTask("日常任务"), _FakeTask("自动送货")]
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "\\ok-ef\\daily", "日常任务", actions="main.py -t 1 -e",
            xml_config=_xml_with("main.py -t 1 -e"), task_index=1),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 0
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert saved["\\ok-ef\\daily"]["task_index"] == 1
    assert registered == []


def test_rewrites_current_process_argv(isolated, monkeypatch):
    """校正后应改写本次进程 sys.argv，使本次启动也使用新索引。"""
    patch_mod, cache_file, registered = isolated
    onetime_tasks = [_FakeTask("日常任务"), _FakeTask("自动送货")]
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "\\ok-ef\\daily", "日常任务", actions="main.py -t 15 -e",
            xml_config=_xml_with("main.py -t 15 -e"), task_index=15),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["main.py", "-t", "15", "-e"])

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 1
    assert sys.argv == ["main.py", "-t", "1", "-e"]


def test_rewrite_argv_direct(monkeypatch):
    """_rewrite_current_process_argv：数字与任务名形式都能改写。"""
    monkeypatch.setattr(sys, "argv", ["main.py", "-t", "15", "-e"])
    sync_patch._rewrite_current_process_argv({"15": 3})
    assert sys.argv == ["main.py", "-t", "3", "-e"]

    monkeypatch.setattr(sys, "argv", ["main.py", "-t", "日常任务", "-e"])
    sync_patch._rewrite_current_process_argv({"日常任务": 3})
    assert sys.argv == ["main.py", "-t", "3", "-e"]

    # 无关参数不动
    monkeypatch.setattr(sys, "argv", ["main.py", "-e"])
    sync_patch._rewrite_current_process_argv({"15": 3})
    assert sys.argv == ["main.py", "-e"]


def test_sync_guard_once_per_process(isolated):
    """每次进程只校正一次：guard 阻止第二次校正。"""
    patch_mod, cache_file, registered = isolated
    onetime_tasks = [_FakeTask("日常任务")]

    def write_stale():
        data = {
            "\\ok-ef\\daily": _make_cache_entry(
                "\\ok-ef\\daily", "日常任务", actions="main.py -t 15 -e",
                xml_config=_xml_with("main.py -t 15 -e"), task_index=15),
        }
        cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    write_stale()
    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 1
    assert len(registered) == 1

    # 重新写入同样的旧状态，guard 应阻止再次校正
    write_stale()
    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 0
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert saved["\\ok-ef\\daily"]["task_index"] == 15
    assert len(registered) == 1


def test_no_cache_no_op(isolated):
    """缓存文件不存在时直接返回 0，不调 COM。"""
    patch_mod, cache_file, registered = isolated
    onetime_tasks = [_FakeTask("日常任务")]
    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 0
    assert registered == []


def test_empty_onetime_tasks_no_op(isolated):
    """onetime_tasks 为空时不校正。"""
    patch_mod, cache_file, registered = isolated
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "\\ok-ef\\daily", "日常任务", actions="main.py -t 15 -e",
            xml_config=_xml_with("main.py -t 15 -e"), task_index=15),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=[]) == 0
    assert registered == []


def test_default_reads_from_og_executor(isolated, monkeypatch):
    """不传 onetime_tasks 时自动从 og.executor.onetime_tasks 读取。"""
    patch_mod, cache_file, registered = isolated
    monkeypatch.setattr(patch_mod, "_onetime_tasks", lambda: [_FakeTask("日常任务")])
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "\\ok-ef\\daily", "日常任务", actions="main.py -t 15 -e",
            xml_config=_xml_with("main.py -t 15 -e"), task_index=15),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes() == 1
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert saved["\\ok-ef\\daily"]["task_index"] == 1


def test_rewrite_from_xml_only(isolated):
    """actions 无 -t 但 xml_config 有 -t 时也能校正。"""
    patch_mod, cache_file, registered = isolated
    onetime_tasks = [_FakeTask("日常任务")]
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "\\ok-ef\\daily", "日常任务", actions="main.py",
            xml_config=_xml_with("main.py -t 15 -e"), task_index=15),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 1
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    entry = saved["\\ok-ef\\daily"]
    assert entry["task_index"] == 1
    assert "-t 1" in entry["xml_config"]
    assert registered == [("\\ok-ef\\daily", entry["xml_config"])]
