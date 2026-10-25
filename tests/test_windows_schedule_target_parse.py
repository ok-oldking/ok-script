"""
windows_schedule -t 目标解析辅助函数的单元测试。

覆盖 extract_task_target / parse_task_target_fields：
强制同步（COM / schtasks）解析 Windows 计划任务时，用它们回填
ScheduleTaskInfo 的 task_index / task_identifier，避免缓存元数据被冲掉。
"""

from ok.util.windows_schedule import extract_task_target, parse_task_target_fields, resolve_schedule_task_index


def test_extract_task_target_from_actions():
    assert extract_task_target("python.exe main.py -t 3 -e") == "3"
    assert extract_task_target("python.exe main.py -t src.tasks.onetime.Daily -e") == \
        "src.tasks.onetime.Daily"


def test_extract_task_target_from_xml_arguments():
    xml = '<Arguments>main.py -t 1 -e</Arguments>'
    assert extract_task_target(xml) == "1"
    xml2 = '<Arguments>main.py -t a.b.CDaily -e</Arguments>'
    assert extract_task_target(xml2) == "a.b.CDaily"


def test_extract_task_target_prefers_actions_then_xml():
    # actions 无 -t 时回退到 xml_config（如 stop_others + main.py 双动作任务）
    assert extract_task_target(
        'python.exe "stop_others.py" --keep "ok-end-field"',
        "<Arguments>main.py -t 1 -e</Arguments>",
    ) == "1"
    # actions 命中时不再看 xml
    assert extract_task_target("main.py -t 5", "<Arguments>main.py -t 9</Arguments>") == "5"


def test_extract_task_target_no_match():
    assert extract_task_target() is None
    assert extract_task_target("", None) is None
    assert extract_task_target('python.exe "stop_others.py" --keep "x"') is None
    # -t 后无值不算命中
    assert extract_task_target("main.py -t") is None


def test_parse_task_target_fields_defaults():
    assert parse_task_target_fields() == (-1, "")
    assert parse_task_target_fields("", "") == (-1, "")
    assert parse_task_target_fields('python.exe "stop_others.py"') == (-1, "")


def test_parse_task_target_fields_numeric_index():
    xml = '<?xml version="1.0"?><Arguments>main.py -t 12 -e</Arguments>'
    assert parse_task_target_fields(xml_config=xml) == (12, "")
    assert parse_task_target_fields(actions="main.py -t 2 -e") == (2, "")


def test_parse_task_target_fields_identifier():
    xml = "<Arguments>main.py -t src.tasks.onetime.DailyTask -e</Arguments>"
    assert parse_task_target_fields(xml_config=xml) == (-1, "src.tasks.onetime.DailyTask")


def test_parse_task_target_fields_legacy_name_not_mapped():
    # 历史任务名格式无法静态映射为稳定标识，返回默认值
    xml = "<Arguments>main.py -t 日常任务 -e</Arguments>"
    assert parse_task_target_fields(xml_config=xml) == (-1, "")


def test_resolve_identifier_after_reorder_and_module_move():
    daily = type("Daily", (), {"__module__": "tasks.new"})()
    other = type("Other", (), {})()
    assert resolve_schedule_task_index("tasks.new.Daily", [other, daily]) == 2
    assert resolve_schedule_task_index("tasks.old.Daily", [daily, other]) == 1
    duplicate = type("Daily", (), {"__module__": "tasks.other"})()
    assert resolve_schedule_task_index("tasks.old.Daily", [daily, duplicate]) == -1
    assert resolve_schedule_task_index("tasks.new.Daily", [daily, duplicate]) == 1
