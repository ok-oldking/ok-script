import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from ok import og
from ok.core.mcp_runner import McpTaskRunner, TERMINAL_STATES
from ok.core.task_manager import TaskManager
from ok.util.config import Config
from test_executor_jobs import make_test_executor


@pytest.fixture
def development(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Config, 'config_folder', str(tmp_path / 'configs'))
    frame = np.zeros((20, 30, 3), dtype=np.uint8)
    capture = SimpleNamespace(connected=lambda: True, get_frame=lambda busy_wait=0: frame.copy())
    interaction = SimpleNamespace(should_capture=lambda: True, on_run=Mock(), on_destroy=Mock())
    executor = make_test_executor(capture, interaction)
    app = SimpleNamespace(state={}, events=[], started=threading.Event(), release=threading.Event(),
                          debug=False, locale='en_US')
    monkeypatch.setattr(og, 'config', {})
    manager = TaskManager(executor, app)
    monkeypatch.setattr(og, 'task_manager', manager)
    screens = SimpleNamespace(screenshot_folder=str(tmp_path / 'screenshots'),
                              to_pil_image=lambda image: Image.fromarray(image[:, :, ::-1]))
    runner = McpTaskRunner(executor, app, screens, tmp_path / 'artifacts', task_manager=manager)
    yield SimpleNamespace(runner=runner, executor=executor, app=app, root=tmp_path,
                          capture=capture, screens=screens, manager=manager)
    app.release.set()
    runner.close()
    executor.stop()
    if executor.thread is not None:
        executor.thread.join(3)
        assert not executor.thread.is_alive()
    import sys
    for name, module in tuple(sys.modules.items()):
        if str(getattr(module, '__file__', '')).startswith(str(tmp_path)):
            sys.modules.pop(name, None)


def write_task(root, body="self._app.state['value'] = 'first'", *, reset=None, verify=None):
    path = root / 'attempt.py'
    source = f'''from ok import BaseTask

class Task(BaseTask):
    def reset_to_start(self):
        {reset or "self._app.state.clear()"}
        self._app.events.append('reset')

    def verify_start_state(self):
        {verify or "assert not self._app.state"}
        self._app.events.append('verify')

    def run(self):
        self._app.events.append('run')
        {body}

    def on_destroy(self):
        self._app.events.append('cleanup')
'''
    path.write_text(source, encoding='utf-8')
    return path


def register_task(dev, name='registered_task'):
    path = dev.root / f'{name}.py'
    path.write_text('''from ok import BaseTask
class RegisteredTask(BaseTask):
    value = 'first'
    def run(self): self._app.state['value'] = self.value
    def on_destroy(self): self._app.events.append('registered_cleanup')
''', encoding='utf-8')
    task = dev.manager.load_single_user_task(str(path))
    assert task is not None
    return path, task


def wait_run(runner, run_id):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        status = runner.get_run_status(run_id)
        if status['state'] in TERMINAL_STATES:
            return status
        time.sleep(0.01)
    pytest.fail(f'Run did not finish: {status}')


def test_fail_edit_reset_and_rerun_loads_current_source(development):
    dev = development
    path = write_task(dev.root, "self._app.state['value'] = 'dirty'; assert False, 'expected failure'")
    first = wait_run(dev.runner, dev.runner.run_task(str(path))['run_id'])
    assert first['state'] == 'failed'
    assert 'expected failure' in Path(first['log_path']).read_text(encoding='utf-8')
    assert dev.app.state == {'value': 'dirty'}

    write_task(dev.root, "self.log_info('second attempt'); self._app.state['value'] = 'fixed'")
    second = wait_run(dev.runner, dev.runner.run_task(str(path))['run_id'])
    assert second['state'] == 'succeeded'
    assert dev.app.state == {'value': 'fixed'}
    assert dev.app.events == ['reset', 'verify', 'run', 'cleanup'] * 2
    assert second['source_sha256'] != first['source_sha256']
    assert 'second attempt' in Path(second['log_path']).read_text(encoding='utf-8')
    assert json.loads((Path(second['artifact_directory']) / 'status.json').read_text()) == second
    assert dev.executor.exclusive_owner is None
    assert dev.executor.device_manager.interaction.on_run.call_count == 2


@pytest.mark.parametrize('reset,verify', [
    ("raise RuntimeError('reset failed')", None),
    ('return False', None),
    (None, 'return False'),
    (None, "assert False, 'wrong page'"),
])
def test_failed_reset_or_verification_blocks_main_task(development, reset, verify):
    dev = development
    path = write_task(dev.root, reset=reset, verify=verify)
    status = wait_run(dev.runner, dev.runner.run_task(str(path))['run_id'])
    assert status['state'] == 'failed'
    assert 'run' not in dev.app.events
    assert dev.app.events[-1] == 'cleanup'
    assert dev.executor.exclusive_owner is None


def test_cancellation_keeps_ownership_until_code_and_cleanup_exit(development):
    dev = development
    path = write_task(dev.root, 'self._app.started.set(); self._app.release.wait(3); self.sleep(0)')
    run_id = dev.runner.run_task(str(path))['run_id']
    assert dev.app.started.wait(2)
    assert dev.runner.stop_task(run_id)['state'] == 'stopping'
    with pytest.raises(RuntimeError, match='still active'):
        dev.runner.run_task(str(path))
    assert dev.executor.exclusive_owner == f'mcp:{run_id}'
    dev.app.release.set()
    assert wait_run(dev.runner, run_id)['state'] == 'cancelled'
    assert dev.app.events[-1] == 'cleanup'
    assert dev.executor.exclusive_owner is None


def test_screenshot_while_running_returns_independent_cached_frame(development):
    dev = development
    path = write_task(dev.root, 'self.executor.next_frame(); self._app.started.set(); self._app.release.wait(3)')
    run_id = dev.runner.run_task(str(path))['run_id']
    assert dev.app.started.wait(2)
    # The screenshot tool must not invoke this backend on the calling thread.
    dev.capture.get_frame = Mock(side_effect=AssertionError('unsafe concurrent capture'))
    observation = dev.runner.screenshot()
    assert observation['cached'] is True
    assert observation['width'] == 30 and observation['height'] == 20
    assert Path(observation['path']).is_absolute()
    with Image.open(observation['path']) as image:
        assert image.size == (30, 20)
    dev.executor.get_frame_snapshot()[0][:] = 255
    assert not dev.executor.get_frame_snapshot()[0].any()
    dev.app.release.set()
    assert wait_run(dev.runner, run_id)['state'] == 'succeeded'


def test_idle_screenshot_captures_fresh_frame(development):
    dev = development
    observation = dev.runner.screenshot()
    assert observation['cached'] is False
    assert Path(observation['path']).exists()
    assert dev.executor.paused


@pytest.mark.parametrize('source', [
    'this is invalid Python!',
    'from ok import BaseTask\nclass Task(BaseTask):\n    def run(self): pass',
    'from ok import TriggerTask\nclass Task(TriggerTask): pass',
])
def test_invalid_file_fails_without_retaining_executor(development, source):
    dev = development
    path = dev.root / 'invalid.py'
    path.write_text(source)
    status = wait_run(dev.runner, dev.runner.run_task(str(path))['run_id'])
    assert status['state'] == 'failed'
    assert status['error']
    assert dev.executor.exclusive_owner is None


def test_same_size_same_timestamp_edit_does_not_reuse_bytecode(development):
    import os
    dev = development
    path = write_task(dev.root)
    original_time = path.stat().st_mtime_ns
    first = dev.runner.run_task(str(path))['run_id']
    assert wait_run(dev.runner, first)['state'] == 'succeeded'
    path.write_text(path.read_text().replace("'first'", "'other'"))
    os.utime(path, ns=(original_time, original_time))
    second = dev.runner.run_task(str(path))['run_id']
    assert wait_run(dev.runner, second)['state'] == 'succeeded'
    assert dev.app.state['value'] == 'other'


def test_cleanup_finishes_before_another_attempt_can_start(development):
    dev = development
    path = write_task(dev.root)
    path.write_text(path.read_text().replace(
        "self._app.events.append('cleanup')",
        "self._app.started.set(); self._app.release.wait(3); self._app.events.append('cleanup')"))
    run_id = dev.runner.run_task(str(path))['run_id']
    assert dev.app.started.wait(2)
    assert dev.runner.get_run_status(run_id)['state'] == 'running'
    with pytest.raises(RuntimeError, match='still active'):
        dev.runner.run_task(str(path))
    dev.app.release.set()
    assert wait_run(dev.runner, run_id)['state'] == 'succeeded'
    assert dev.app.events[-1] == 'cleanup'


def test_cancel_queued_attempt_never_loads_or_runs_the_file(development):
    dev = development

    def occupy():
        dev.app.started.set()
        dev.app.release.wait(3)

    first = dev.executor.submit(occupy)
    assert dev.app.started.wait(2)
    path = write_task(dev.root)
    run_id = dev.runner.run_task(str(path))['run_id']
    assert dev.runner.stop_task(run_id)['state'] == 'cancelled'
    assert dev.app.events == []
    assert dev.executor.exclusive_owner is None
    dev.app.release.set()
    first.future.result(2)


def test_idle_capture_failure_does_not_return_an_old_frame_as_fresh(development):
    dev = development
    dev.runner.screenshot()
    dev.executor.next_frame = lambda time_out: None
    with pytest.raises(RuntimeError, match='fresh target frame'):
        dev.runner.screenshot()


def test_task_disable_stops_execution_at_next_framework_check(development):
    dev = development
    path = write_task(dev.root,
                      "self.disable(); self.sleep(0.01); self._app.events.append('unexpected action')")
    status = wait_run(dev.runner, dev.runner.run_task(str(path))['run_id'])
    assert status['state'] == 'cancelled'
    assert 'unexpected action' not in dev.app.events
    assert dev.app.events[-1] == 'cleanup'
    assert dev.executor.current_task is None
    assert dev.executor.exclusive_owner is None


def test_task_sleep_checks_run_inside_exclusive_job(development):
    dev = development
    path = write_task(dev.root,
                      "self.sleep_check_interval = 0; self.sleep(0.01)")
    with path.open('a', encoding='utf-8') as output:
        output.write("\n    def sleep_check(self):\n"
                     "        assert self.executor.current_task is self\n"
                     "        self._app.events.append('sleep_check')\n")
    status = wait_run(dev.runner, dev.runner.run_task(str(path))['run_id'])
    assert status['state'] == 'succeeded', status
    assert 'sleep_check' in dev.app.events
    assert dev.executor.current_task is None


def test_cleanup_failure_clears_task_context_before_next_attempt(development):
    dev = development
    path = write_task(dev.root)
    path.write_text(path.read_text().replace(
        "self._app.events.append('cleanup')", "raise RuntimeError('cleanup failed')"))
    status = wait_run(dev.runner, dev.runner.run_task(str(path))['run_id'])
    assert status['state'] == 'failed'
    assert 'cleanup failed' in status['error']
    assert dev.executor.current_task is None
    assert dev.executor.exclusive_owner is None

    write_task(dev.root)
    status = wait_run(dev.runner, dev.runner.run_task(str(path))['run_id'])
    assert status['state'] == 'succeeded', status


def test_closing_runner_cancels_work_and_prevents_new_attempts(development):
    dev = development
    path = write_task(dev.root, 'self._app.started.set(); self._app.release.wait(3); self.sleep(0)')
    run_id = dev.runner.run_task(str(path))['run_id']
    assert dev.app.started.wait(2)
    dev.runner.close()
    assert dev.runner.get_run_status(run_id)['state'] == 'stopping'
    with pytest.raises(RuntimeError, match='shutting down'):
        dev.runner.run_task(str(path))
    dev.app.release.set()
    assert wait_run(dev.runner, run_id)['state'] == 'cancelled'


def test_discover_edit_reload_and_run_existing_task(development):
    import os
    dev = development
    path, old = register_task(dev)
    _, other = register_task(dev, 'untouched_task')
    entry, _ = dev.runner.list_tasks()
    assert entry['task_id'] == 'registered_task.RegisteredTask'
    assert entry['file_path'] == str(path)
    assert entry['kind'] == 'onetime' and entry['plugin'] is None
    stamp = path.stat().st_mtime_ns
    path.write_text(path.read_text().replace("'first'", "'other'"))
    os.utime(path, ns=(stamp, stamp))
    record = dev.runner.reload_tasks([entry['task_id']])
    assert record['operation'] == 'reload_tasks'
    status = wait_run(dev.runner, record['run_id'])
    assert status['state'] == 'succeeded', status
    assert status['result'][0]['task_id'] == entry['task_id']
    assert dev.executor.onetime_tasks[0] is not old
    assert dev.executor.onetime_tasks[1] is other
    assert dev.app.events == ['registered_cleanup']
    assert dev.executor.exclusive_owner is None
    assert json.loads(Path(status['artifact_directory'], 'status.json').read_text()) == status
    harness = write_task(dev.root,
        "from registered_task import RegisteredTask; "
        "self.get_task_by_class(RegisteredTask).run(); assert self._app.state['value'] == 'other'")
    result = wait_run(dev.runner, dev.runner.run_task(str(harness))['run_id'])
    assert result['state'] == 'succeeded', result
    assert dev.app.state['value'] == 'other'


def test_reload_all_returns_all_replacements(development):
    dev = development
    _, first = register_task(dev)
    _, second = register_task(dev, 'other_task')
    status = wait_run(dev.runner, dev.runner.reload_tasks()['run_id'])
    assert status['state'] == 'succeeded', status
    assert len(status['result']) == 2
    assert first not in dev.executor.onetime_tasks and second not in dev.executor.onetime_tasks


def test_failed_reload_keeps_original_and_records_traceback(development):
    dev = development
    path, old = register_task(dev)
    path.write_text('invalid syntax !!!!')
    status = wait_run(dev.runner, dev.runner.reload_tasks()['run_id'])
    assert status['state'] == 'failed'
    assert 'SyntaxError' in status['error']
    assert 'SyntaxError' in Path(status['log_path']).read_text()
    assert dev.executor.onetime_tasks == [old]
    assert not dev.app.events
    assert dev.executor.exclusive_owner is None


@pytest.mark.parametrize('ids', [['missing.Task'], ['RegisteredTask'], 'registered_task.RegisteredTask', [1]])
def test_invalid_reload_selection_does_not_take_ownership(development, ids):
    dev = development
    _, old = register_task(dev)
    old._enabled = True
    with pytest.raises((TypeError, ValueError)):
        dev.runner.reload_tasks(ids)
    assert old.enabled
    assert dev.executor.exclusive_owner is None
    assert dev.executor.onetime_tasks == [old]


def test_reload_rejects_active_file_run(development):
    dev = development
    register_task(dev)
    path = write_task(dev.root, 'self._app.started.set(); self._app.release.wait(3)')
    run_id = dev.runner.run_task(str(path))['run_id']
    assert dev.app.started.wait(2)
    with pytest.raises(RuntimeError, match='still active'):
        dev.runner.reload_tasks()
    dev.app.release.set()
    assert wait_run(dev.runner, run_id)['state'] == 'succeeded'


def test_running_reload_finishes_transaction_before_releasing_ownership(development, monkeypatch):
    dev = development
    _, old = register_task(dev)
    dispatch = dev.manager._dispatch_reload
    def blocked_reload(tasks):
        dev.app.started.set()
        assert dev.app.release.wait(3)
        return dispatch(tasks)
    monkeypatch.setattr(dev.manager, '_dispatch_reload', blocked_reload)
    run_id = dev.runner.reload_tasks()['run_id']
    assert dev.app.started.wait(2)
    with pytest.raises(RuntimeError, match='still active'):
        dev.runner.run_task(str(write_task(dev.root)))
    assert dev.runner.stop_task(run_id)['state'] == 'stopping'
    assert dev.executor.exclusive_owner == f'mcp:{run_id}'
    dev.app.release.set()
    status = wait_run(dev.runner, run_id)
    assert status['state'] == 'succeeded', status
    assert old not in dev.executor.onetime_tasks
    assert dev.executor.exclusive_owner is None


def test_cancel_queued_reload_does_not_replace_tasks(development):
    dev = development
    _, old = register_task(dev)
    first = dev.executor.submit(lambda: (dev.app.started.set(), dev.app.release.wait(3)))
    assert dev.app.started.wait(2)
    run_id = dev.runner.reload_tasks()['run_id']
    assert dev.runner.stop_task(run_id)['state'] == 'cancelled'
    assert dev.executor.onetime_tasks == [old]
    assert not dev.app.events
    dev.app.release.set()
    first.future.result(2)
