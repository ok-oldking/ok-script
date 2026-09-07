"""Platform routing tests; never invoke a system scheduler or touch user config."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ok.util import windows_schedule as schedule


@pytest.fixture
def scheduler_dependencies(monkeypatch):
    cache = Mock()
    cache.get_all.return_value = [schedule.ScheduleTaskInfo(name="saved", enabled=True)]
    monkeypatch.setattr(schedule, "WindowsScheduleCache", Mock(return_value=cache))
    run = Mock(side_effect=AssertionError("System scheduler CLI must not run"))
    monkeypatch.setattr(schedule.subprocess, "run", run)
    return cache, run


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_unsupported_scheduler_does_not_sync_or_mutate(monkeypatch, scheduler_dependencies, caplog, platform):
    cache, run = scheduler_dependencies
    monkeypatch.setattr(schedule, "sys", SimpleNamespace(platform=platform))
    with caplog.at_level("INFO"):
        manager = schedule.WindowsScheduleManager({"gui_title": "test"})
    assert "NATIVE_SCHEDULER_UNSUPPORTED" in caplog.text
    assert not manager.is_supported()
    assert not manager.is_com_available()
    assert manager.query_all_tasks() == []
    assert manager.query_all_tasks(force_sync=True) == []
    assert manager.sync_tasks(force=True) is None
    manager.start_background_sync()
    assert not manager.running
    assert manager.sync_thread is None
    assert not manager.create_task("saved", 0, schedule.TriggerType.DAILY)
    assert not manager.replace_task("saved", 0, schedule.TriggerType.DAILY)
    assert not manager.delete_task("saved")
    assert not manager.enable_task("saved")
    assert not manager.disable_task("saved")
    assert cache.mock_calls == []
    run.assert_not_called()


@pytest.mark.parametrize("com_available", [False, True])
def test_windows_query_routing_and_cache_unchanged(monkeypatch, scheduler_dependencies, com_available):
    cache, run = scheduler_dependencies
    monkeypatch.setattr(schedule, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(schedule.WindowsScheduleManager, "_init_com_service", Mock())
    manager = schedule.WindowsScheduleManager({"gui_title": "test"})
    manager.SCHEDULE_SERVICE = object() if com_available else None
    assert manager.is_supported()
    assert manager.is_com_available() == com_available
    assert manager.query_all_tasks() == cache.get_all.return_value
    task = schedule.ScheduleTaskInfo(name="fresh")
    manager._query_tasks_via_com = Mock(return_value=[task])
    manager._query_tasks_via_schtasks = Mock(return_value=[task])
    assert manager.query_all_tasks(force_sync=True) == [task]
    chosen = manager._query_tasks_via_com if com_available else manager._query_tasks_via_schtasks
    chosen.assert_called_once_with()
    cache.clear.assert_called_once_with()
    cache.add_or_update.assert_called_once_with(task)
    run.assert_not_called()


def test_windows_create_still_uses_existing_backend(monkeypatch, scheduler_dependencies):
    cache, run = scheduler_dependencies
    monkeypatch.setattr(schedule, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(schedule.WindowsScheduleManager, "_init_com_service", Mock())
    manager = schedule.WindowsScheduleManager({"gui_title": "test"})
    manager.SCHEDULE_SERVICE = None
    manager._create_task_via_schtasks = Mock(return_value=True)
    assert manager.create_task("new task", 0, schedule.TriggerType.DAILY)
    manager._create_task_via_schtasks.assert_called_once()
    cache.add_or_update.assert_called_once()
    run.assert_not_called()


def test_unsupported_decorated_operation_never_enters_com(monkeypatch, scheduler_dependencies):
    monkeypatch.setattr(schedule, 'sys', SimpleNamespace(platform='darwin'))
    manager = schedule.WindowsScheduleManager({'gui_title': 'test'})
    manager._com_session = Mock(side_effect=AssertionError('COM must not be initialized'))
    assert not manager.create_task('test', 0, schedule.TriggerType.DAILY)
    assert not manager._delete_task_by_path('synthetic')
    assert not manager._set_task_enabled('synthetic', True)
    manager._com_session.assert_not_called()


def test_com_failure_fallback_preserves_upstream_stable_task_identity(monkeypatch, scheduler_dependencies):
    import sys
    client = SimpleNamespace()
    monkeypatch.setitem(sys.modules, 'win32com', SimpleNamespace(client=client))
    monkeypatch.setitem(sys.modules, 'win32com.client', client)
    manager = schedule.WindowsScheduleManager({'gui_title': 'test'})
    manager.is_com_available = Mock(return_value=True)
    manager._generate_task_xml = Mock(return_value='<Task/>')
    manager.SCHEDULE_SERVICE = SimpleNamespace(Connect=Mock(side_effect=RuntimeError('synthetic failure')))
    manager._create_task_via_schtasks = Mock(return_value=True)
    assert manager._create_task_via_com(
        'task', 1, schedule.TriggerType.DAILY, 2, 9, 0, True, True,
        'description', 'synthetic-path', 0, 0, 'src.task.Task')
    manager._create_task_via_schtasks.assert_called_once_with(
        'task', 1, schedule.TriggerType.DAILY, True, 'synthetic-path',
        2, 9, 0, True, 0, 0, 'description', 'src.task.Task')
