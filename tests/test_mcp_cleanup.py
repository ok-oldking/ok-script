import json
import os
import time
import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest

from ok.core.mcp_runner import McpTaskRunner
from test_mcp_runner import development, wait_run, write_task


def saved_run(root, *, state='succeeded', age=8, **fields):
    path = root / uuid.uuid4().hex
    path.mkdir(parents=True)
    record = {'run_id': path.name, 'state': state, 'finished_at': time.time() - age * 86400, **fields}
    (path / 'status.json').write_text(json.dumps(record), encoding='utf-8')
    (path / 'run.log').write_text('evidence', encoding='utf-8')
    (path / 'custom').mkdir()
    (path / 'custom' / 'image.png').write_bytes(b'custom evidence')
    return path


def observation(root, age):
    path = root / 'observations' / f'{uuid.uuid4().hex}.png'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'image')
    modified = time.time() - age * 86400
    os.utime(path, (modified, modified))
    return path


def runner_at(root, **kwargs):
    return McpTaskRunner(Mock(), Mock(), Mock(), root, **kwargs)


def test_startup_expires_completed_runs_and_observations_only(tmp_path):
    old = [saved_run(tmp_path, state=state) for state in ('succeeded', 'failed', 'cancelled')]
    recent = saved_run(tmp_path, age=1)
    unfinished = [saved_run(tmp_path, state=state) for state in ('queued', 'running', 'stopping')]
    old_image = observation(tmp_path, 8)
    recent_image = observation(tmp_path, 1)
    connections = tmp_path / 'connections'
    connections.mkdir()
    connection = connections / '1-8765.json'
    connection.write_text('{}')
    compatibility = tmp_path / 'connection.json'
    compatibility.write_text('{}')
    unknown = tmp_path / 'notes'
    unknown.mkdir()
    (unknown / 'notes.txt').write_text('keep')
    unknown_image = tmp_path / 'observations' / 'manual.png'
    unknown_image.write_bytes(b'keep')
    os.utime(unknown_image, (0, 0))

    runner_at(tmp_path)

    assert all(not path.exists() for path in old)
    assert not old_image.exists()
    assert all(path.exists() for path in [recent, *unfinished, recent_image, connection,
                                          compatibility, unknown / 'notes.txt', unknown_image])


@pytest.mark.parametrize('contents', ['{', '[]', '{"state": []}', None])
def test_cleanup_preserves_incomplete_or_malformed_run_records(tmp_path, contents):
    path = saved_run(tmp_path)
    status = path / 'status.json'
    if contents is None:
        status.unlink()
    else:
        status.write_text(contents)
    runner_at(tmp_path)
    assert (path / 'run.log').exists()


@pytest.mark.parametrize('fields', [{'state': []}, {'finished_at': None}, {'finished_at': '0'},
                                  {'finished_at': float('nan')}, {'run_id': 'different'}])
def test_cleanup_preserves_unusable_status_metadata(tmp_path, fields):
    path = saved_run(tmp_path, **fields)
    runner_at(tmp_path)
    assert (path / 'run.log').exists()


def test_retention_can_be_configured_or_disabled(tmp_path):
    path = saved_run(tmp_path, age=3)
    image = observation(tmp_path, 3)
    runner_at(tmp_path, retention_days=0)
    assert path.exists() and image.exists()
    runner_at(tmp_path, retention_days=2)
    assert not path.exists() and not image.exists()


@pytest.mark.parametrize('retention', [-1, None, '7', True, float('nan'), float('inf')])
def test_invalid_retention_is_rejected(tmp_path, retention):
    with pytest.raises(ValueError, match='retention_days'):
        runner_at(tmp_path, retention_days=retention)


def test_cleanup_during_activity_is_throttled_and_expires_memory(development):
    dev = development
    task = write_task(dev.root)
    status = wait_run(dev.runner, dev.runner.run_task(str(task))['run_id'])
    run_id = status['run_id']
    record = dev.runner._runs[run_id]['record']
    record['finished_at'] = time.time() - 8 * 86400
    dev.runner._save(record)
    path = Path(status['artifact_directory'])

    # The startup sweep already ran, so requests within the hour leave it alone.
    dev.runner.screenshot()
    assert path.exists()
    dev.runner._next_cleanup = 0
    dev.runner.screenshot()
    assert not path.exists()
    with pytest.raises(ValueError, match='Unknown run_id'):
        dev.runner.get_run_status(run_id)

    old = saved_run(dev.runner.artifact_directory)
    dev.runner._next_cleanup = 0
    assert wait_run(dev.runner, dev.runner.run_task(str(task))['run_id'])['state'] == 'succeeded'
    assert not old.exists()


def test_cleanup_preserves_active_run_even_with_old_terminal_record(development):
    dev = development
    task = write_task(dev.root, 'self.executor.next_frame(); self._app.started.set(); self._app.release.wait(3)')
    run_id = dev.runner.run_task(str(task))['run_id']
    assert dev.app.started.wait(2)
    path = Path(dev.runner.get_run_status(run_id)['artifact_directory'])
    (path / 'status.json').write_text(json.dumps({
        'run_id': run_id, 'state': 'succeeded', 'finished_at': 0}))
    dev.runner._next_cleanup = 0
    dev.runner.screenshot()
    assert (path / 'run.log').exists()
    dev.app.release.set()
    assert wait_run(dev.runner, run_id)['state'] == 'succeeded'


def test_cleanup_failure_does_not_block_other_artifacts(tmp_path, monkeypatch):
    path = saved_run(tmp_path)
    image = observation(tmp_path, 8)
    monkeypatch.setattr('ok.core.mcp_runner.shutil.rmtree', Mock(side_effect=PermissionError('locked')))
    runner_at(tmp_path)
    assert path.exists()
    assert not image.exists()


def test_cleanup_does_not_follow_directory_junctions(tmp_path):
    import subprocess

    if os.name != 'nt':
        pytest.skip('Windows directory junctions')
    outside = tmp_path / 'outside'
    saved = saved_run(outside)
    observation(outside, 8)
    root = tmp_path / 'mcp'
    root.mkdir()
    # A junction needs no elevated symlink privilege on Windows.
    for link, target in [(root / saved.name, saved), (root / 'observations', outside / 'observations')]:
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    runner_at(root)
    assert (saved / 'run.log').exists()
    assert len(list((outside / 'observations').glob('*.png'))) == 1
