"""
计划任务索引启动校正补丁的单元测试（完全隔离）。

不依赖 ok 全局（onetime_tasks 通过参数 / monkeypatch 传入假任务列表），
不调用真实 Windows COM（monkeypatch `_register_task_xml`），
缓存文件使用 tmp_path（monkeypatch `_cache_file`）。

校正语义：所有可定位的 -t 目标统一迁移为稳定标识（模块路径.类名），
并回填缓存的 task_index / task_identifier 元数据。
"""

import json
import sys

import pytest

import ok.ui.qt.tasks.schedule_index_sync as sync_patch

# 用于生成唯一类名的假任务（模块路径.类名 即稳定标识，必须互不相同）
_class_seq = iter(range(100000))


def _make_task(name):
    """创建带唯一类名的假任务实例。"""
    cls = type(
        f"_GenTask{next(_class_seq)}",
        (),
        {"__init__": lambda self, n=name: setattr(self, "name", n)},
    )
    return cls()


def _identifier(task):
    """任务的稳定标识（模块路径.类名）。"""
    return f"{task.__class__.__module__}.{task.__class__.__name__}"


def _make_cache_entry(path, name, actions="", xml_config="", task_index=-1,
                      task_identifier=""):
    entry = {
        "path": path,
        "name": name,
        "actions": actions,
        "xml_config": xml_config,
        "task_index": task_index,
        "enabled": True,
        "status": "Ready",
        "trigger_type": "Daily",
    }
    if task_identifier is not None:
        entry["task_identifier"] = task_identifier
    return entry


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
        sync_patch, "_register_task_xml", lambda path, xml: registered.append((path, xml)) or True
    )
    yield sync_patch, cache_file, registered
    sync_patch.reset_sync_guard()


def test_replace_task_target():
    """改写 -t 目标：数字、XML 结尾、任务名、稳定标识、空串。"""
    assert sync_patch._replace_task_target("main.py -t 15 -e", 3) == "main.py -t 3 -e"
    assert (
        sync_patch._replace_task_target("<Arguments>main.py -t 15</Arguments>", 3)
        == "<Arguments>main.py -t 3</Arguments>"
    )
    assert (
        sync_patch._replace_task_target("<Arguments>main.py -t 日常任务 -e</Arguments>", 3)
        == "<Arguments>main.py -t 3 -e</Arguments>"
    )
    assert (
        sync_patch._replace_task_target("main.py -t 15 -e", "src.tasks.onetime.DailyTask")
        == "main.py -t src.tasks.onetime.DailyTask -e"
    )
    assert sync_patch._replace_task_target("", 3) == ""


def test_launch_resolution_does_not_wait_for_windows_migration(isolated, monkeypatch):
    from types import SimpleNamespace
    from ok import og

    sync, cache_file, registered = isolated
    task = _make_task("Daily")
    entry = _make_cache_entry("\\ok-ef\\Daily", "Daily",
                              actions="main.py -t 5 -e",
                              xml_config=_xml_with("main.py -t 5 -e"))
    original = json.dumps({entry["path"]: entry})
    cache_file.write_text(original, encoding="utf-8")
    monkeypatch.setattr(sync, "_onetime_tasks", lambda: [task])
    monkeypatch.setattr(sys, "argv", ["main.py", "-t", "5", "-e"])
    monkeypatch.setattr(og, "ok", SimpleNamespace(args={"task": 5}))

    sync.resolve_current_schedule_task()

    assert sys.argv[2] == _identifier(task)
    assert og.ok.args["task"] == _identifier(task)
    assert registered == []
    assert cache_file.read_text(encoding="utf-8") == original
    # Migration must not overwrite arguments after runtime has already started.
    monkeypatch.setattr(sys, "argv", ["main.py", "-t", "5"])
    og.ok.args["task"] = 5
    assert sync.sync_schedule_task_indexes([task], rewrite_argv=False) == 1
    assert sys.argv[2] == "5"
    assert og.ok.args["task"] == 5
    assert len(registered) == 1


def test_extract_task_target():
    """从 actions / xml_config 提取当前 -t 目标（索引、任务名或稳定标识）。"""
    item = _make_cache_entry("\\ok-ef\\x", "日常任务", actions="main.py -t 15 -e", task_index=15)
    assert sync_patch._extract_task_target(item) == "15"

    item2 = _make_cache_entry(
        "\\ok-ef\\x", "日常任务", xml_config=_xml_with("main.py -t 日常任务")
    )
    assert sync_patch._extract_task_target(item2) == "日常任务"

    identifier = "src.tasks.onetime.DailyTask"
    item3 = _make_cache_entry(
        "\\ok-ef\\x", "日常任务", actions=f"main.py -t {identifier} -e"
    )
    assert sync_patch._extract_task_target(item3) == identifier

    item4 = _make_cache_entry("\\ok-ef\\x", "日常任务")
    assert sync_patch._extract_task_target(item4) is None


def test_rewrites_stale_index_to_identifier(isolated):
    """旧索引（-t 15）应按 name 定位并迁移为稳定标识，同时回填元数据。"""
    patch_mod, cache_file, registered = isolated
    daily = _make_task("日常任务")
    ident = _identifier(daily)
    onetime_tasks = [daily, _make_task("自动送货"), _make_task("影拓丰碑")]
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
    assert entry["task_identifier"] == ident
    assert f"-t {ident}" in entry["actions"]
    assert f"-t {ident}" in entry["xml_config"]
    assert "-t 15" not in entry["actions"]
    assert "-t 15" not in entry["xml_config"]
    # Windows 计划任务用新 XML 同步注册
    assert registered == [("\\ok-ef\\daily_abc", entry["xml_config"])]


def test_rewrites_historical_name_target(isolated):
    """历史迁移成的任务名 -t 也应迁移为稳定标识。"""
    patch_mod, cache_file, registered = isolated
    daily = _make_task("日常任务")
    ident = _identifier(daily)
    onetime_tasks = [daily, _make_task("自动送货")]
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
    assert entry["task_identifier"] == ident
    assert f"-t {ident}" in entry["actions"]
    assert "-t 日常任务" not in entry["actions"]
    assert registered


def test_migrates_already_correct_numeric_index(isolated):
    """即使数字索引当前正确（如 -t 1），也应迁移为稳定标识并回填元数据。

    对应用户实际场景：缓存 task_index=-1 / task_identifier=""，
    actions 是 stop_others 命令（无 -t），XML 中为 main.py -t 1 -e。
    """
    patch_mod, cache_file, registered = isolated
    daily = _make_task("日常任务")
    ident = _identifier(daily)
    onetime_tasks = [daily, _make_task("自动送货")]
    data = {
        "\\ok-ef\\日常任务_6fad503f": _make_cache_entry(
            "\\ok-ef\\日常任务_6fad503f",
            "日常任务",
            actions='python.exe "stop_others.py" --keep "ok-end-field"',
            xml_config=_xml_with("main.py -t 1 -e"),
            task_index=-1,
        )
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 1

    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    entry = saved["\\ok-ef\\日常任务_6fad503f"]
    assert entry["task_index"] == 1
    assert entry["task_identifier"] == ident
    assert f"-t {ident}" in entry["xml_config"]
    assert "-t 1" not in entry["xml_config"]
    # actions 无 -t，保持不变
    assert "--keep" in entry["actions"]
    assert len(registered) == 1


def test_multiple_tasks_corrected(isolated):
    """多个任务各自按 name 迁移为对应的稳定标识。"""
    patch_mod, cache_file, registered = isolated
    tasks = [_make_task(n) for n in
             ["日常任务", "x2", "x3", "自动送货", "x5", "x6", "影拓丰碑", "启动一次游戏"]]
    idents = {t.name: _identifier(t) for t in tasks}
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

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=tasks) == 4

    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    expected = {
        "\\ok-ef\\daily": ("日常任务", 1),
        "\\ok-ef\\deliver": ("自动送货", 4),
        "\\ok-ef\\monument": ("影拓丰碑", 7),
        "\\ok-ef\\once": ("启动一次游戏", 8),
    }
    for path, (name, index) in expected.items():
        entry = saved[path]
        assert entry["task_index"] == index
        assert entry["task_identifier"] == idents[name]
        assert f"-t {idents[name]}" in entry["actions"]
    assert len(registered) == 4


def test_registration_failure_keeps_cache_and_retries(isolated, monkeypatch):
    """Windows 任务注册失败时（COM 与 schtasks 都失败）不得改写缓存。

    失败的条目保持旧目标，changed 为 0，下次启动会重试。
    """
    patch_mod, cache_file, registered = isolated
    onetime_tasks = [_make_task("日常任务"), _make_task("自动送货")]
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "\\ok-ef\\daily", "日常任务", actions="main.py -t 15 -e",
            xml_config=_xml_with("main.py -t 15 -e"), task_index=15),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(patch_mod, "_register_task_xml", lambda path, xml: False)
    monkeypatch.setattr(patch_mod, "_register_task_xml_via_schtasks", lambda path, xml: False)

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 0
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    entry = saved["\\ok-ef\\daily"]
    # 注册失败则不改缓存：仍为旧目标，task_identifier 也保持为空
    assert entry["task_index"] == 15
    assert entry["task_identifier"] == ""
    assert "-t 15" in entry["actions"]
    assert "-t 15" in entry["xml_config"]
    assert registered == []


def test_registration_failure_does_not_rewrite_current_argv(isolated, monkeypatch):
    """注册失败时不得改写本次进程 sys.argv / og.ok.args。"""
    patch_mod, cache_file, registered = isolated
    onetime_tasks = [_make_task("日常任务"), _make_task("自动送货")]
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "\\ok-ef\\daily", "日常任务", actions="main.py -t 15 -e",
            xml_config=_xml_with("main.py -t 15 -e"), task_index=15),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(patch_mod, "_register_task_xml", lambda path, xml: False)
    monkeypatch.setattr(sys, "argv", ["main.py", "-t", "15", "-e"])

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 0
    assert sys.argv == ["main.py", "-t", "15", "-e"]


def test_skips_other_app_read_only_tasks(isolated):
    """其它 ok-* 应用的任务（只读）不应被改写。"""
    patch_mod, cache_file, registered = isolated
    onetime_tasks = [_make_task("日常任务")]
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
    onetime_tasks = [_make_task("日常任务")]
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

def test_skips_entry_without_path(isolated):
    """缓存条目无 path 时跳过，不写缓存不调 COM（避免缓存与系统不一致）。"""
    patch_mod, cache_file, registered = isolated
    daily = _make_task("日常任务")
    onetime_tasks = [daily, _make_task("自动送货")]
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "", "日常任务", actions="main.py -t 15 -e",
            xml_config=_xml_with("main.py -t 15 -e"), task_index=15),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 0
    assert registered == []
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    entry = saved["\\ok-ef\\daily"]
    assert entry["task_index"] == 15
    assert "-t 15" in entry["xml_config"]


def test_skips_duplicate_task_name(isolated):
    """重名任务时跳过 name 匹配，不静默迁移到错误的同名任务。"""
    patch_mod, cache_file, registered = isolated
    # 两个同名任务（不同类）
    onetime_tasks = [_make_task("日常任务"), _make_task("日常任务")]
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "\\ok-ef\\daily", "日常任务", actions="main.py -t 15 -e",
            xml_config=_xml_with("main.py -t 15 -e"), task_index=15),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 0
    assert registered == []
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert saved["\\ok-ef\\daily"]["task_index"] == 15


def test_name_to_index_map_does_not_confuse_name_with_class():
    """任务名与其它任务的类名相同时，不应被误判为重名并移除。"""
    t1 = _make_task("日常任务")
    t2 = _make_task(t1.__class__.__name__)  # t2 的名字 = t1 的类名
    mapping = sync_patch._name_to_index_map([t1, t2])
    # t1 的类名（= t2 的名字）不应被当作重名移除
    assert t1.__class__.__name__ in mapping
    assert mapping["日常任务"] == 1


def test_skips_when_xml_has_no_replaceable_target(isolated):
    """xml_config 无 -t 可替换时跳过（new_xml == old_xml），避免缓存与系统不一致。"""
    patch_mod, cache_file, registered = isolated
    daily = _make_task("日常任务")
    onetime_tasks = [daily, _make_task("自动送货")]
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "\\ok-ef\\daily", "日常任务",
            actions="main.py -t 15 -e",
            xml_config=_xml_with("main.py -e"),  # xml 无 -t
            task_index=15),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 0
    assert registered == []
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    entry = saved["\\ok-ef\\daily"]
    assert entry["task_index"] == 15
    assert "-t 15" in entry["actions"]
    # xml_config 必须保持不变（跳过注册时不得改写 XML）
    assert entry["xml_config"] == data["\\ok-ef\\daily"]["xml_config"]

def test_digit_target_resolved_by_cached_identifier_when_name_missing(isolated):
    """数字目标 + 任务名缺失时，回退用缓存的稳定标识定位目标任务。"""
    patch_mod, cache_file, registered = isolated
    deliver = _make_task("自动送货")
    ident = _identifier(deliver)
    onetime_tasks = [_make_task("别的任务"), deliver]
    data = {
        "\\ok-ef\\legacy": _make_cache_entry(
            "\\ok-ef\\legacy", "已不存在的名字", actions="main.py -t 9 -e",
            xml_config=_xml_with("main.py -t 9 -e"), task_index=9,
            task_identifier=ident),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 1
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    entry = saved["\\ok-ef\\legacy"]
    assert entry["task_index"] == 2
    assert entry["task_identifier"] == ident
    assert f"-t {ident}" in entry["xml_config"]


def test_idempotent_fully_normalized(isolated):
    """目标与元数据均已正确时不写缓存、不调 COM。"""
    patch_mod, cache_file, registered = isolated
    daily = _make_task("日常任务")
    ident = _identifier(daily)
    onetime_tasks = [daily, _make_task("自动送货")]
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "\\ok-ef\\daily", "日常任务", actions=f"main.py -t {ident} -e",
            xml_config=_xml_with(f"main.py -t {ident} -e"), task_index=1,
            task_identifier=ident),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 0
    assert registered == []


def test_backfills_metadata_without_rewrite(isolated):
    """-t 已是正确稳定标识但缺少元数据时，仅回填缓存，不调 COM。"""
    patch_mod, cache_file, registered = isolated
    daily = _make_task("日常任务")
    ident = _identifier(daily)
    onetime_tasks = [daily, _make_task("自动送货")]
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "\\ok-ef\\daily", "日常任务", actions=f"main.py -t {ident} -e",
            xml_config=_xml_with(f"main.py -t {ident} -e"),
            task_index=-1, task_identifier=""),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 1
    assert registered == []
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    entry = saved["\\ok-ef\\daily"]
    assert entry["task_index"] == 1
    assert entry["task_identifier"] == ident
    # XML 未被改写
    assert entry["xml_config"] == _xml_with(f"main.py -t {ident} -e")


def test_rewrites_current_process_argv(isolated, monkeypatch):
    """校正后应改写本次进程 sys.argv，使本次启动也使用新目标（稳定标识）。"""
    patch_mod, cache_file, registered = isolated
    daily = _make_task("日常任务")
    ident = _identifier(daily)
    onetime_tasks = [daily, _make_task("自动送货")]
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "\\ok-ef\\daily", "日常任务", actions="main.py -t 15 -e",
            xml_config=_xml_with("main.py -t 15 -e"), task_index=15),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["main.py", "-t", "15", "-e"])

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 1
    assert sys.argv == ["main.py", "-t", ident, "-e"]


def test_rewrite_argv_direct(monkeypatch):
    """_rewrite_current_process_argv：数字与任务名形式都能改写为稳定标识。"""
    monkeypatch.setattr(sys, "argv", ["main.py", "-t", "15", "-e"])
    sync_patch._rewrite_current_process_argv({"15": "src.tasks.onetime.Daily"})
    assert sys.argv == ["main.py", "-t", "src.tasks.onetime.Daily", "-e"]

    monkeypatch.setattr(sys, "argv", ["main.py", "-t", "日常任务", "-e"])
    sync_patch._rewrite_current_process_argv({"日常任务": "a.b.C"})
    assert sys.argv == ["main.py", "-t", "a.b.C", "-e"]

    # 无关参数不动
    monkeypatch.setattr(sys, "argv", ["main.py", "-e"])
    sync_patch._rewrite_current_process_argv({"15": "a.b.C"})
    assert sys.argv == ["main.py", "-e"]


def test_sync_guard_once_per_process(isolated):
    """每次进程只校正一次：guard 阻止第二次校正。"""
    patch_mod, cache_file, registered = isolated
    onetime_tasks = [_make_task("日常任务")]

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
    onetime_tasks = [_make_task("日常任务")]
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
    daily = _make_task("日常任务")
    monkeypatch.setattr(patch_mod, "_onetime_tasks", lambda: [daily])
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "\\ok-ef\\daily", "日常任务", actions="main.py -t 15 -e",
            xml_config=_xml_with("main.py -t 15 -e"), task_index=15),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes() == 1
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    entry = saved["\\ok-ef\\daily"]
    assert entry["task_index"] == 1
    assert entry["task_identifier"] == _identifier(daily)


def test_rewrite_from_xml_only(isolated):
    """actions 无 -t 但 xml_config 有 -t 时也能校正。"""
    patch_mod, cache_file, registered = isolated
    daily = _make_task("日常任务")
    ident = _identifier(daily)
    onetime_tasks = [daily]
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
    assert f"-t {ident}" in entry["xml_config"]
    assert registered == [("\\ok-ef\\daily", entry["xml_config"])]


def test_module_path_identifier_no_change_but_metadata_backfilled(isolated):
    """模块路径标识已正确时无需重注册 Windows 任务，但会回填缺失的元数据。"""
    patch_mod, cache_file, registered = isolated
    daily = _make_task("日常任务")
    ident = _identifier(daily)
    onetime_tasks = [daily]
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "\\ok-ef\\daily", "日常任务", actions=f"main.py -t {ident} -e",
            xml_config=_xml_with(f"main.py -t {ident} -e"), task_index=-1),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 1
    assert registered == []
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    entry = saved["\\ok-ef\\daily"]
    assert f"-t {ident}" in entry["actions"]
    assert entry["task_index"] == 1
    assert entry["task_identifier"] == ident


def test_module_path_class_name_fallback(isolated):
    """模块路径变化（模块移动/重命名）时，类名回退匹配并修正为新模块路径。"""
    patch_mod, cache_file, registered = isolated
    daily = _make_task("日常任务")
    onetime_tasks = [daily]
    current_identifier = _identifier(daily)
    # 旧的错误模块路径：模块变了，但类名还在
    stale_identifier = f"old.broken.module.{daily.__class__.__name__}"
    data = {
        "\\ok-ef\\daily": _make_cache_entry(
            "\\ok-ef\\daily", "日常任务", actions=f"main.py -t {stale_identifier} -e",
            xml_config=_xml_with(f"main.py -t {stale_identifier} -e"), task_index=-1),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert patch_mod.sync_schedule_task_indexes(onetime_tasks=onetime_tasks) == 1
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    entry = saved["\\ok-ef\\daily"]
    assert f"-t {current_identifier}" in entry["actions"]
    assert f"-t {current_identifier}" in entry["xml_config"]
    assert f"-t {stale_identifier}" not in entry["actions"]
    assert entry["task_index"] == 1
    assert entry["task_identifier"] == current_identifier
    assert registered == [("\\ok-ef\\daily", entry["xml_config"])]
