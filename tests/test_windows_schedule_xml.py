"""
windows_schedule 计划任务 XML 生成测试。

覆盖 _generate_task_xml 的 Settings 部分：
机器休眠/关机期间错过的计划任务，应在机器恢复可用后自动补跑
（StartWhenAvailable = true，对应 GitHub issue #98）。
"""

from ok.util.windows_schedule import (
    WindowsScheduleManager,
    TriggerType,
)


def _build_manager():
    """构造一个不依赖真实 Windows 任务计划服务的管理器实例。"""
    return WindowsScheduleManager.__new__(WindowsScheduleManager)


def _generate(trigger_type: TriggerType, **kwargs) -> str:
    """调用 _generate_task_xml 生成 XML 字符串。"""
    manager = _build_manager()
    return manager._generate_task_xml(
        task_name="TestTask",
        task_index=1,
        trigger_type=trigger_type,
        **kwargs,
    )


def test_start_when_available_is_true():
    """错过计划时间的任务应在机器恢复后补跑（#98）。"""
    xml = _generate(TriggerType.DAILY)
    assert "<StartWhenAvailable>true</StartWhenAvailable>" in xml
    assert "<StartWhenAvailable>false</StartWhenAvailable>" not in xml


def test_start_when_available_true_for_all_trigger_types():
    """所有触发器类型生成的 XML 都应包含补跑设置。"""
    for trigger_type in TriggerType:
        xml = _generate(trigger_type)
        assert "<StartWhenAvailable>true</StartWhenAvailable>" in xml, \
            f"{trigger_type} 缺少 StartWhenAvailable=true"


def test_settings_section_well_formed():
    """Settings 块应保持合法的任务计划 XML 结构。"""
    xml = _generate(TriggerType.WEEKLY, start_hour=9, start_minute=30)
    assert "<Settings>" in xml and "</Settings>" in xml
    # Settings 块内 StartWhenAvailable 应成对出现（开/闭标签）且值为 true
    settings = xml.split("<Settings>")[1].split("</Settings>")[0]
    assert settings.count("StartWhenAvailable") == 2  # <tag> + </tag>
    assert "<StartWhenAvailable>true</StartWhenAvailable>" in settings
