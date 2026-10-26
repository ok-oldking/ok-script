import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from ok.core import plugin_staging as staging
from ok.core.plugins import PLUGIN_SOURCE_FILE, read_plugin_source
from ok.core.script_packager import scan_import_folders


def install_old(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / 'ok_import/demo'
    target.mkdir(parents=True)
    (target / 'manifest.json').write_text(json.dumps({'file_name': 'demo', 'version': '1.0', 'tasks': []}))
    (target / 'old.txt').write_text('old version')
    return target


def package(tmp_path, *, files=None, manifest=None):
    archive = tmp_path / 'update.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('demo/manifest.json', json.dumps(manifest or {
            'file_name': 'demo', 'version': '2.0', 'tasks': [],
        }))
        for name, body in (files or {'new.txt': 'new version'}).items():
            output.writestr('demo/' + name, body)
    return archive


def change_folder(tmp_path):
    return tmp_path / 'ok_import' / staging.STAGING_FOLDER / 'demo'


def test_update_staging_preserves_current_files_and_survives_archive_removal(tmp_path, monkeypatch):
    target = install_old(tmp_path, monkeypatch)
    archive = package(tmp_path)
    source = {'repository': 'owner/repo', 'tag': 'v2.0', 'asset_name': 'demo.zip'}
    result = staging.install_or_stage_plugin(archive, source)
    assert result['restart_required']
    assert (target / 'old.txt').read_text() == 'old version'
    assert not (target / 'new.txt').exists()
    assert scan_import_folders()[0]['version'] == '1.0'
    incoming = change_folder(tmp_path) / 'incoming'
    assert read_plugin_source(incoming) == source
    archive.unlink()
    staging.apply_pending_plugin_changes()
    assert (target / 'new.txt').read_text() == 'new version'
    assert (change_folder(tmp_path) / 'previous/old.txt').exists()
    assert staging.pending_plugin_changes()['demo']['phase'] == 'validating'
    staging.finish_plugin_update('demo')
    assert staging.pending_plugin_changes() == {}
    assert not change_folder(tmp_path).exists()


def test_delete_is_only_applied_on_next_launch_and_preserves_external_data(tmp_path, monkeypatch):
    target = install_old(tmp_path, monkeypatch)
    user_data = tmp_path / 'configs/plugin_data/demo'
    user_data.mkdir(parents=True)
    (user_data / 'data.json').write_text('keep')
    staging.stage_plugin_delete('demo')
    assert target.exists()
    assert scan_import_folders()[0]['file_name'] == 'demo'
    staging.apply_pending_plugin_changes()
    assert not target.exists()
    assert staging.pending_plugin_changes() == {}
    assert (user_data / 'data.json').read_text() == 'keep'


@pytest.mark.parametrize('action', ['update', 'delete'])
def test_pending_changes_can_be_cancelled_without_mutating_installation(tmp_path, monkeypatch, action):
    target = install_old(tmp_path, monkeypatch)
    if action == 'update':
        staging.stage_plugin_update(package(tmp_path))
    else:
        staging.stage_plugin_delete('demo')
    with pytest.raises(ValueError, match='pending change'):
        staging.stage_plugin_delete('demo')
    staging.cancel_pending_plugin_change('demo')
    assert staging.pending_plugin_changes() == {}
    assert (target / 'old.txt').exists()


@pytest.mark.parametrize('failure_point', ['backup', 'activate'])
def test_apply_failure_restores_previous_files(tmp_path, monkeypatch, failure_point):
    target = install_old(tmp_path, monkeypatch)
    staging.stage_plugin_update(package(tmp_path))
    original = staging.os.replace
    def fail(source, destination):
        if ((failure_point == 'backup' and Path(destination).name == 'previous')
                or (failure_point == 'activate' and Path(source).name == 'incoming')):
            raise PermissionError('synthetic file lock')
        return original(source, destination)
    monkeypatch.setattr(staging.os, 'replace', fail)
    staging.apply_pending_plugin_changes()
    assert (target / 'old.txt').read_text() == 'old version'
    assert not (target / 'new.txt').exists()
    assert staging.pending_plugin_changes()['demo']['phase'] == 'failed'
    assert 'synthetic file lock' in staging.pending_plugin_changes()['demo']['error']


def test_unconfirmed_or_failed_update_rolls_back_on_following_launch(tmp_path, monkeypatch):
    target = install_old(tmp_path, monkeypatch)
    staging.stage_plugin_update(package(tmp_path))
    staging.apply_pending_plugin_changes()
    assert (target / 'new.txt').exists()
    staging.finish_plugin_update('demo', error='Plugin initialization failed')
    assert staging.pending_plugin_changes()['demo']['phase'] == 'rollback'
    with pytest.raises(ValueError, match='recovery'):
        staging.cancel_pending_plugin_change('demo')
    staging.apply_pending_plugin_changes()
    assert (target / 'old.txt').exists()
    assert staging.pending_plugin_changes()['demo']['phase'] == 'failed'
    staging.cancel_pending_plugin_change('demo')
    assert target.exists()


def test_crash_before_initialization_confirmation_restores_old_version(tmp_path, monkeypatch):
    target = install_old(tmp_path, monkeypatch)
    staging.stage_plugin_update(package(tmp_path))
    staging.apply_pending_plugin_changes()
    # No success acknowledgement: model a crashed process and another launch.
    staging.apply_pending_plugin_changes()
    assert (target / 'old.txt').exists()
    assert staging.pending_plugin_changes()['demo']['phase'] == 'failed'


def test_interrupted_backup_move_is_recovered(tmp_path, monkeypatch):
    target = install_old(tmp_path, monkeypatch)
    staging.stage_plugin_update(package(tmp_path))
    folder = change_folder(tmp_path)
    operation = staging.pending_plugin_changes()['demo']
    operation.update(phase='applying', had_previous=True)
    staging._write_operation(folder, operation)
    os.replace(target, folder / 'previous')
    staging.apply_pending_plugin_changes()
    assert (target / 'old.txt').exists()
    assert staging.pending_plugin_changes()['demo']['phase'] == 'failed'


def test_corrupted_staged_manifest_does_not_move_good_installation(tmp_path, monkeypatch):
    target = install_old(tmp_path, monkeypatch)
    staging.stage_plugin_update(package(tmp_path))
    (change_folder(tmp_path) / 'incoming/manifest.json').unlink()
    staging.apply_pending_plugin_changes()
    assert (target / 'old.txt').exists()
    assert staging.pending_plugin_changes()['demo']['phase'] == 'failed'


def test_failed_trash_cleanup_does_not_reactivate_deleted_plugin(tmp_path, monkeypatch):
    target = install_old(tmp_path, monkeypatch)
    staging.stage_plugin_delete('demo')
    original = staging.shutil.rmtree
    def fail(path, *args, **kwargs):
        if Path(path).name == 'previous':
            raise PermissionError('locked previous version')
        return original(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(staging.shutil, 'rmtree', fail)
        staging.apply_pending_plugin_changes()
    assert not target.exists()
    assert scan_import_folders() == []
    assert staging.pending_plugin_changes()['demo']['phase'] == 'committed'
    staging.apply_pending_plugin_changes()
    assert not target.exists()
    assert staging.pending_plugin_changes() == {}


def test_delete_rename_failure_keeps_original_installation(tmp_path, monkeypatch):
    target = install_old(tmp_path, monkeypatch)
    staging.stage_plugin_delete('demo')
    original = staging.os.replace
    def fail(source, destination):
        if Path(destination).name == 'previous':
            raise PermissionError('installation is locked')
        return original(source, destination)
    monkeypatch.setattr(staging.os, 'replace', fail)
    staging.apply_pending_plugin_changes()
    assert (target / 'old.txt').exists()
    assert scan_import_folders()[0]['file_name'] == 'demo'
    assert staging.pending_plugin_changes()['demo']['phase'] == 'failed'


def test_corrupt_journal_blocks_only_affected_plugin(tmp_path, monkeypatch):
    target = install_old(tmp_path, monkeypatch)
    staging.stage_plugin_delete('demo')
    (change_folder(tmp_path) / 'operation.json').write_text('broken')
    assert staging.pending_plugin_changes()['demo']['phase'] == 'recovery'
    assert scan_import_folders() == []
    assert (target / 'old.txt').exists()
    staging.apply_pending_plugin_changes()
    assert staging.pending_plugin_changes()['demo']['phase'] == 'recovery'
    assert scan_import_folders() == []


def test_interrupted_preparation_is_cleaned_without_affecting_active_plugin(tmp_path, monkeypatch):
    target = install_old(tmp_path, monkeypatch)
    preparation = target.parent / staging.STAGING_FOLDER / '.prepare-interrupted'
    preparation.mkdir(parents=True)
    (preparation / 'payload').write_text('incomplete upload')
    staging.apply_pending_plugin_changes()
    assert not preparation.exists()
    assert (target / 'old.txt').exists()


def test_staging_rejects_traversal_identifiers(tmp_path, monkeypatch):
    install_old(tmp_path, monkeypatch)
    outside = tmp_path / 'outside'
    outside.mkdir()
    with pytest.raises(ValueError):
        staging.stage_plugin_delete('../outside')
    assert outside.exists()


@pytest.mark.parametrize('mode', ['headless', 'qt', 'broken_task', 'broken_tab'])
def test_real_fresh_process_applies_then_validates_before_committing_backup(tmp_path, monkeypatch, mode):
    target = install_old(tmp_path, monkeypatch)
    manifest = {'file_name': 'demo', 'version': '2.0', 'tasks': []}
    files = {'new.txt': 'new version'}
    if mode in {'qt', 'broken_tab'}:
        manifest['custom_tabs'] = [['page', 'Page']]
        files['page.py'] = ('from PySide6.QtWidgets import QWidget\nclass Page(QWidget):\n'
                            '    def __init__(self):\n' +
                            ('        raise RuntimeError("broken tab")\n' if mode == 'broken_tab'
                             else '        super().__init__()\n'))
    elif mode == 'broken_task':
        manifest['tasks'] = [['entry', 'Task']]
        files['entry.py'] = ('from ok import BaseTask\nfrom pathlib import Path\nclass Task(BaseTask):\n'
                             '    def __init__(self, *args, **kwargs): pass\n'
                             '    def after_init(self, **kwargs): raise RuntimeError("broken task")\n'
                             '    def on_destroy(self): Path("task-cleanup.txt").write_text("closed")\n')
    staging.stage_plugin_update(package(tmp_path, manifest=manifest, files=files))
    source = '''
import os, sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0, sys.argv[1])
os.chdir(sys.argv[2])
sys.modules['packaging'] = None
from ok import og
from ok.core.plugin_staging import apply_pending_plugin_changes, pending_plugin_changes
from ok.core.task_manager import TaskManager
mode = sys.argv[3]
apply_pending_plugin_changes()
assert pending_plugin_changes()['demo']['phase'] == 'validating'
assert Path('ok_import/.plugin-staging/demo/previous/old.txt').exists()
manager = TaskManager.__new__(TaskManager)
manager.imported_scripts, manager.task_map, manager.task_errors = {}, {}, {}
manager.task_executor = SimpleNamespace(onetime_tasks=[], trigger_tasks=[], current_task=None, feature_set=None)
manager.app = SimpleNamespace(debug=False)
manager.scene = None
manager.defer_plugin_validation = mode in ('qt', 'broken_tab')
og.task_manager, og.executor = manager, manager.task_executor
manager.load_imported_tasks()
if mode in ('qt', 'broken_tab'):
    assert pending_plugin_changes()['demo']['phase'] == 'validating'
    from PySide6.QtWidgets import QApplication, QWidget, QStackedWidget
    from ok.ui.qt.plugins.imported_tabs import ImportedTabs
    app = QApplication([])
    window = QWidget()
    window.executor = manager.task_executor
    window.app = SimpleNamespace(tr=lambda text: text)
    window.navigationInterface = Mock()
    window.stackedWidget = QStackedWidget(window)
    window.imported_tabs = {}
    window.addSubInterface = lambda widget, *args, **kwargs: window.stackedWidget.addWidget(widget)
    window.update_navigation_width = Mock()
    controller = ImportedTabs(window)
    controller.refresh()
    controller.dispose()
if mode.startswith('broken'):
    assert pending_plugin_changes()['demo']['phase'] == 'rollback'
    assert Path('ok_import/.plugin-staging/demo/previous/old.txt').exists()
else:
    assert pending_plugin_changes() == {}
    assert not Path('ok_import/.plugin-staging/demo').exists()
'''
    result = subprocess.run(
        [sys.executable, '-c', source, str(Path(__file__).resolve().parents[1]), str(tmp_path), mode],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    if mode.startswith('broken'):
        if mode == 'broken_task':
            assert (tmp_path / 'task-cleanup.txt').read_text() == 'closed'
        staging.apply_pending_plugin_changes()
        assert (target / 'old.txt').exists()
    else:
        assert (target / 'new.txt').exists()
