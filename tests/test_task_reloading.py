import importlib
import os
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ok import og
from ok.core.task_manager import TaskManager
from ok.util.config import Config
from test_executor_jobs import make_test_executor


SOURCE = '''from ok import BaseTask, TriggerTask
class FirstTask(BaseTask):
    value = 'first'
    def on_destroy(self):
        self._app.events.append(('destroy', self))
class SecondTask(FirstTask): pass
class WatchTask(TriggerTask):
    def on_destroy(self):
        self._app.events.append(('destroy', self))
'''


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(Config, 'config_folder', str(tmp_path / 'config'))
    capture = SimpleNamespace(connected=lambda: True)
    executor = make_test_executor(capture, SimpleNamespace(on_destroy=Mock()))
    app = SimpleNamespace(debug=True, locale='en_US', tr=lambda text: text, events=[])
    monkeypatch.setattr(og, 'config', {})
    manager = TaskManager(executor, app)
    monkeypatch.setattr(og, 'task_manager', manager)
    monkeypatch.setattr(og, 'executor', executor)
    yield SimpleNamespace(root=tmp_path, executor=executor, app=app, manager=manager)
    executor.stop()
    if executor.thread is not None:
        executor.thread.join(3)
        assert not executor.thread.is_alive()
    for name, module in tuple(sys.modules.items()):
        source = str(getattr(module, '__file__', ''))
        if source.startswith(str(tmp_path)) or name.startswith('_ok_plugin_') and not hasattr(module, '__file__'):
            sys.modules.pop(name, None)


def register(runtime, name='reload_example', source=SOURCE, classes=('FirstTask',)):
    path = runtime.root / (name + '.py')
    path.write_text(source, encoding='utf-8')
    module = importlib.import_module(name)
    for cls_name in classes:
        task = getattr(module, cls_name)(executor=runtime.executor, app=runtime.app)
        task.after_init(executor=runtime.executor)
        task.post_init()
        tasks = runtime.executor.trigger_tasks if cls_name == 'WatchTask' else runtime.executor.onetime_tasks
        tasks.append(task)
    return path, module


def test_debug_and_custom_tasks_never_create_a_watcher(runtime, monkeypatch):
    watcher = Mock()
    monkeypatch.setattr(og, 'config', {'custom_tasks': True})
    manager = TaskManager(runtime.executor, runtime.app, file_watcher_factory=watcher)
    watcher.assert_not_called()
    assert not hasattr(manager, '_debug_watcher')


def test_reload_never_reexecutes_the_application_entry_point(tmp_path):
    path = tmp_path / 'main.py'
    path.write_text('raise AssertionError("application entry point executed")')
    original = sys.modules.get('__main__')
    with pytest.raises(ValueError, match='importable module'):
        TaskManager._load_source_module('__main__', path)
    assert sys.modules.get('__main__') is original


def test_selected_module_reloads_once_and_keeps_other_modules(runtime):
    path, module = register(runtime, classes=('FirstTask', 'SecondTask'))
    register(runtime, 'untouched')
    first, second, untouched = runtime.executor.onetime_tasks
    path.write_text(SOURCE.replace("'first'", "'other'"), encoding='utf-8')
    replacements = runtime.manager.reload_tasks([first, module.SecondTask]).future.result(3)
    assert len(replacements) == 2
    assert runtime.executor.onetime_tasks[2] is untouched
    new_module = sys.modules[module.__name__]
    assert type(replacements[0]) is new_module.FirstTask
    assert type(replacements[1]) is new_module.SecondTask
    assert type(replacements[1]).__bases__ == (new_module.FirstTask,)
    assert replacements[0].value == 'other'
    assert runtime.executor.get_task_by_class(module.FirstTask) is replacements[0]
    assert runtime.app.events == [('destroy', first), ('destroy', second)]


def test_same_size_same_timestamp_edit_ignores_bytecode(runtime):
    path, module = register(runtime)
    stamp = path.stat().st_mtime_ns
    assert list(runtime.root.rglob('*.pyc'))
    path.write_text(SOURCE.replace("'first'", "'other'"), encoding='utf-8')
    os.utime(path, ns=(stamp, stamp))
    replacement, = runtime.manager.reload_tasks().future.result(3)
    assert replacement.value == 'other'
    assert type(replacement) is sys.modules[module.__name__].FirstTask


@pytest.mark.parametrize('broken', [
    'invalid syntax !!!!',
    SOURCE + '\nFirstTask.post_init = lambda self: 1 / 0\n',
    SOURCE + '\nFirstTask = object\n',
])
def test_failed_custom_reload_preserves_task_and_module(runtime, broken):
    path = runtime.root / 'custom_task.py'
    path.write_text(SOURCE)
    old = runtime.manager.load_single_user_task(str(path))
    module = sys.modules[type(old).__module__]
    path.write_text(broken)
    with pytest.raises(Exception):
        runtime.manager.reload_task_code(old).future.result(3)
    assert runtime.executor.onetime_tasks == [old]
    assert old in runtime.manager.task_map
    assert sys.modules[type(old).__module__] is module
    assert ('destroy', old) not in runtime.app.events
    assert str(path) in runtime.manager.task_errors
    path.write_text(SOURCE.replace("'first'", "'fixed'"))
    new, = runtime.manager.reload_task_code(old).future.result(3)
    assert new.value == 'fixed'
    assert old not in runtime.manager.task_map
    assert str(path) not in runtime.manager.task_errors


def test_reload_waits_for_running_code_and_removes_old_queue_entries(runtime):
    register(runtime)
    old, = runtime.executor.onetime_tasks
    old._enabled = True
    runtime.executor.enqueue_onetime_task(old)
    entered, release = threading.Event(), threading.Event()

    def running_code():
        runtime.executor.current_task = old
        try:
            job = old.reload_tasks()
            runtime.app.reload_job = job
            entered.set()
            assert release.wait(3)
            assert not job.future.done()
            assert runtime.executor.onetime_tasks == [old]
            assert not runtime.app.events
        finally:
            runtime.executor.current_task = None

    current = runtime.executor.submit(running_code)
    try:
        assert entered.wait(2)
    finally:
        release.set()
    current.future.result(3)
    replacement, = runtime.app.reload_job.future.result(3)
    assert replacement is not old
    assert not old.enabled
    assert old not in runtime.executor.onetime_task_queue
    assert ('destroy', old) in runtime.app.events


def test_reload_all_preserves_trigger_enabled_setting(runtime):
    register(runtime, classes=('FirstTask', 'WatchTask'))
    old = runtime.executor.trigger_tasks[0]
    old._enabled = True
    old.config['_enabled'] = True
    replacements = runtime.manager.reload_tasks().future.result(3)
    assert len(replacements) == 2
    new, = runtime.executor.trigger_tasks
    assert new is not old and new.enabled and new.config['_enabled']
    assert not old.enabled


def test_all_modules_roll_back_if_one_fails(runtime):
    path, module = register(runtime, 'first_module')
    bad_path, bad_module = register(runtime, 'second_module')
    old_tasks = list(runtime.executor.onetime_tasks)
    path.write_text(SOURCE.replace("'first'", "'other'"))
    bad_path.write_text('bad syntax !!!!')
    with pytest.raises(SyntaxError):
        runtime.manager.reload_tasks().future.result(3)
    assert runtime.executor.onetime_tasks == old_tasks
    assert sys.modules['first_module'] is module
    assert sys.modules['second_module'] is bad_module
    assert all(('destroy', task) not in runtime.app.events for task in old_tasks)


def test_reload_does_not_discover_helper_tasks(runtime):
    register(runtime)
    (runtime.root / 'helper.py').write_text(SOURCE)
    replacements = runtime.manager.reload_tasks().future.result(3)
    assert len(replacements) == 1
    assert 'helper' not in sys.modules


def test_base_task_forwards_selected_classes_and_empty_list(runtime):
    _, module = register(runtime)
    task = runtime.executor.onetime_tasks[0]
    assert task.reload_tasks([]).future.result(3) == []
    new, = task.reload_tasks([module.FirstTask]).future.result(3)
    assert new is not task


def test_dependent_task_modules_reload_after_their_base(runtime):
    _, base = register(runtime, 'z_base')
    _, child = register(runtime, 'a_child', source='from z_base import FirstTask\nclass ChildTask(FirstTask): pass',
                        classes=('ChildTask',))
    replacements = runtime.manager.reload_tasks().future.result(3)
    assert type(replacements[1]).__bases__ == (type(replacements[0]),)


def test_qt_reload_commits_and_destroys_on_gui_thread(runtime, monkeypatch):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from ok.core import events
    from ok.ui.qt.events import QtEventDispatcher
    from ok.ui.qt.tasks.TaskManger import TaskManager as QtTaskManager

    app = QApplication.instance() or QApplication([])
    event_dispatcher = QtEventDispatcher()
    monkeypatch.setattr(events, '_dispatcher', event_dispatcher.dispatch)
    manager = QtTaskManager(runtime.executor, runtime.app)
    register(runtime)
    old = runtime.executor.onetime_tasks[0]
    threads = []
    old.on_destroy = lambda: threads.append(threading.get_ident())
    job = manager.reload_tasks()
    deadline = time.monotonic() + 3
    while not job.future.done() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    new, = job.future.result(0)
    assert new is not old
    assert threads == [threading.get_ident()]


def test_actual_running_task_can_request_its_own_reload(runtime, monkeypatch):
    import ok.task.TaskExecutor as executor_module

    monkeypatch.setattr(executor_module, 'prevent_sleeping', Mock())
    source = SOURCE + '''
def run(self):
    self._app.reload_job = self.reload_tasks()
    self._app.requested.set()
    assert self._app.release.wait(3)
    assert not self._app.reload_job.future.done()
FirstTask.run = run
'''
    register(runtime, source=source)
    old, = runtime.executor.onetime_tasks
    runtime.app.requested, runtime.app.release = threading.Event(), threading.Event()
    runtime.executor._prepare_task_for_run = Mock()
    runtime.executor.next_frame = Mock(return_value=object())
    runtime.executor.next_task = Mock(side_effect=lambda: (
        (old, True, False) if not runtime.app.requested.is_set() else (None, False, False)))
    old._enabled = True
    runtime.executor.start()
    try:
        assert runtime.app.requested.wait(2)
        assert runtime.executor.current_task is old
    finally:
        runtime.app.release.set()
    replacement, = runtime.app.reload_job.future.result(3)
    assert replacement is not old
    assert not old.running and not old.enabled
    assert ('destroy', old) in runtime.app.events


@pytest.mark.parametrize('broken', [False, True])
def test_editor_run_waits_for_successful_reload(runtime, monkeypatch, broken):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from shiboken6 import delete
    from ok.core import events
    from ok.ui.qt.events import QtEventDispatcher
    from ok.ui.qt.tasks.EditTaskTab import EditTaskTab
    from ok.ui.qt.tasks.TaskManger import TaskManager as QtTaskManager
    from ok.ui.qt.util import Alert

    app = QApplication.instance() or QApplication([])
    dispatcher = QtEventDispatcher()
    monkeypatch.setattr(events, '_dispatcher', dispatcher.dispatch)
    manager = QtTaskManager(runtime.executor, runtime.app)
    monkeypatch.setattr(og, 'task_manager', manager)
    monkeypatch.setattr(og, 'app', runtime.app)
    runtime.app.start_controller = SimpleNamespace(start=Mock())
    error = Mock()
    monkeypatch.setattr(Alert, 'alert_error', error)
    path = runtime.root / 'editor_task.py'
    path.write_text(SOURCE)
    old = manager.load_single_user_task(str(path))
    tab = EditTaskTab()
    tab.load_task(old)
    tab._switch_to_task_tab = Mock()
    tab.editor.setPlainText('invalid syntax !!!!' if broken else SOURCE.replace("'first'", "'other'"))
    entered, release = threading.Event(), threading.Event()
    current = runtime.executor.submit(lambda: (entered.set(), release.wait(3)))
    try:
        assert entered.wait(2)
        tab.run_task()
        runtime.app.start_controller.start.assert_not_called()
        release.set()
        current.future.result(3)
        deadline = time.monotonic() + 3
        while not (error.called or runtime.app.start_controller.start.called) and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        if broken:
            assert error.called
            runtime.app.start_controller.start.assert_not_called()
            assert runtime.executor.onetime_tasks == [old]
        else:
            replacement, = runtime.executor.onetime_tasks
            assert replacement is not old and replacement.value == 'other'
            runtime.app.start_controller.start.assert_called_once_with(replacement)
    finally:
        release.set()
        delete(tab)

